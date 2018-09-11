# **************************************************************************
# *
# * Authors:     Marta Martinez (mmmtnez@cnb.csic.es)
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************

import os
import stat
import pyworkflow.protocol.constants as const
from pyworkflow import VERSION_1_2
from pyworkflow.em import PdbFile
from pyworkflow.em.headers import (
    adaptFileToCCP4, START, Ccp4Header)
from convert import (runCCP4Program, getProgram, validVersion)
from refmac_template_map2mtz import \
    template_refmac_preprocess_NOMASK, template_refmac_preprocess_MASK
from refmac_template_refine \
    import template_refmac_refine_MASK, template_refmac_refine_NOMASK
from pyworkflow.em.protocol import EMProtocol
from pyworkflow.protocol.params import PointerParam, IntParam, FloatParam, \
    BooleanParam, StringParam


class CCP4ProtRunRefmac(EMProtocol):
    """ generates files for volumes and FSCs to submit structures to EMDB
    """
    _label = 'refmac'
    _program = ""
    _version = VERSION_1_2
    refmacMap2MtzScriptFileName = "map2mtz_refmac.sh"
    refmacRefineScriptFileName = "refine_refmac.sh"
    OutPdbFileName = "refmac-refined.pdb"
    createMaskLogFileName = "mask.log"
    refineLogFileName = "refine.log"

    REFMAC = 'refmac5'
    PDBSET = 'pdbset'

    def __init__(self, **kwargs):
        EMProtocol.__init__(self, **kwargs)

    # --------------------------- DEFINE param functions ---------------------
    def _defineParams(self, form):
        form.addSection(label='Input')

        form.addParam('inputVolume', PointerParam, label="Input Volume",
                      allowsNull=True, pointerClass='Volume',
                      help='This is the unit cell volume.')
        form.addParam('inputStructure', PointerParam, label="Input PDBx/mmCIF "
                                                            "file",
                      important=True, pointerClass='PdbFile',
                      help='Specify a PDBx/mmCIF object.')
        form.addParam('maxResolution', FloatParam, default=5,
                      label='Max. Resolution (A):',
                      help="Max resolution used in the refinement (Angstroms)."
                           "Use at least the double of the sampling rate ("
                           "Angstroms/pixel)")
        form.addParam('minResolution', FloatParam, default=200,
                      label='Min. Resolution (A):',
                      help="Min resolution used in the refinement "
                           "(Angstroms).")
        form.addParam('generateMaskedVolume', BooleanParam, default=True,
                      label="Generate masked volume",
                      important=True,
                      help='If set to True, the masked volume will be '
                           'generated')
        form.addParam('SFCALCmapradius', FloatParam, default=3,
                      expertLevel=const.LEVEL_ADVANCED,
                      condition='generateMaskedVolume',
                      label='SFCALC mapradius:',
                      help='Specify how much around molecule should be cut '
                           '(Angstroms)')
        form.addParam('SFCALCmradius', FloatParam, default=3,
                      expertLevel=const.LEVEL_ADVANCED,
                      condition='generateMaskedVolume',
                      label='SFCALC mradius:',
                      help='Specify the radius (Angstroms) to calculate the mask')
        form.addParam('nRefCycle', IntParam, default=30,
                      expertLevel=const.LEVEL_ADVANCED,
                      label='Number of refinement iterations:',
                      help='Specify the number of cycles of refinement.\n')
        form.addParam('weightMatrix', FloatParam, default=0.0,
                      expertLevel=const.LEVEL_ADVANCED,
                      label='Matrix refinement weight:',
                      help='Weight between the density map and the chemical '
                           'constraints. Smaller means less weight for the '
                           'EM map. If set to 0, the program makes sure that '
                           'rmsd bond from ideal values is between 0.015 '
                           'and 0.025\n')
        form.addParam('BFactorSet', FloatParam, default=40,
                      expertLevel=const.LEVEL_ADVANCED,
                      label='B Factor:', help='Specify the B factor value '
                                              'prior to refinement')
        form.addParam('extraParams', StringParam, default='',
                      expertLevel=const.LEVEL_ADVANCED,
                      label='Extra parameters: ',
                      help='Extra parameters to *refmac* program, '
                           'the character | creates a new line\n'
                      """
                      HYDR Yes | HOUT Yes
                      """)

    # --------------------------- INSERT steps functions --------------------
    def _insertAllSteps(self):
        self._insertFunctionStep('convertInputStep')
        self._insertFunctionStep('createDataDictStep')
        self._insertFunctionStep('createMapMtzRefmacStep')
        self._insertFunctionStep('executeMapMtzRefmacStep')
        self._insertFunctionStep('createRefineScriptFileStep')
        self._insertFunctionStep('executeRefineRefmacStep')
        self._insertFunctionStep('createRefmacOutputStep')  # create output
        #                                                     pdb file
        self._insertFunctionStep('writeFinalResultsTableStep')  # Print output
        #                                                         results

    # --------------------------- STEPS functions ---------------------------
    def convertInputStep(self):
        """ convert 3Dmaps to MRC '.mrc' format
        """
        # get input 3D map filename
        fnVol = self._getInputVolume()
        inFileName = fnVol.getFileName()
        if inFileName.endswith(":mrc"):
            inFileName.replace(":mrc", "")

        # create local copy of 3Dmap (tmp3DMapFile.mrc)
        localInFileName = self._getVolumeFileName()
        origin = fnVol.getOrigin(force=True).getShifts()
        sampling = fnVol.getSamplingRate()
        adaptFileToCCP4(inFileName, localInFileName, origin, sampling,
                        START)

    def createDataDictStep(self):
        """ Precompute parameters to be used by refmac"""
        localInFileName = self._getVolumeFileName()
        header = Ccp4Header(localInFileName,
                            readHeader=True)
        self.dict = {}
        x, y, z = header.getCellDimensions()
        self.dict['Xlength'] = x
        self.dict['Ylength'] = y
        self.dict['Zlength'] = z
        x, y, z = header.getGridSampling()
        self.dict['XDim'] = x
        self.dict['YDim'] = y
        self.dict['ZDim'] = z
        self.dict['CCP4_HOME'] = os.environ['CCP4_HOME']
        self.dict['REFMAC_BIN'] = getProgram(self.REFMAC)
        self.dict['PDBSET_BIN'] = getProgram(self.PDBSET)
        self.dict['PDBFILE'] = \
            os.path.basename(self.inputStructure.get().getFileName())
        self.dict['PDBDIR'] = os.path.abspath(os.path.dirname(
            self.inputStructure.get().getFileName()))
        self.dict['MAPFILE'] = os.path.abspath(self._getVolumeFileName())

        self.dict['RESOMIN'] = self.minResolution.get()
        self.dict['RESOMAX'] = self.maxResolution.get()
        self.dict['NCYCLE'] = self.nRefCycle.get()
        if self.weightMatrix.get() == 0:
            self.dict['WEIGHT MATRIX'] = 'auto'
        else:
            self.dict['WEIGHT MATRIX'] = str(self.weightMatrix.get())
        self.dict['OUTPUTDIR'] = self._getExtraPath('')
        self.dict['MASKED_VOLUME'] = self._getMapMaskedByPdbBasedMaskFileName()
        self.dict['PDBSET_MASKED'] = self._getPdbsetMaskPDBFileName()
        self.dict['PDBSET_NO_MASKED'] = self._getPdbsetNOMaskPDBFileName()
        self.dict['SFCALC_MAPRADIUS'] = self.SFCALCmapradius.get()
        self.dict['SFCALC_MRADIUS'] = self.SFCALCmradius.get()
        if self.BFactorSet.get() == 0:
            self.dict['BFACTOR_SET'] = "0"
        else:
            self.dict['BFACTOR_SET'] = "%f" % self.BFactorSet.get()
        self.dict['EXTRA_PARAMS'] = self.extraParams.get().replace('|','\n')


    def createMapMtzRefmacStep(self):
        if self.generateMaskedVolume.get():
            script_map2mtz = template_refmac_preprocess_MASK  % self.dict
        else:
            script_map2mtz = template_refmac_preprocess_NOMASK % self.dict
        f_map2mtz = open(self._getMapMtzScriptFileName(), "w")
        f_map2mtz.write(script_map2mtz)
        f_map2mtz.close()
        os.chmod(self._getMapMtzScriptFileName(), stat.S_IEXEC | stat.S_IREAD |
                 stat.S_IWRITE)

    def executeMapMtzRefmacStep(self):
        # Generic is a env variable that coot uses as base dir for some
        # but not all files. "" force a trailing slash
        runCCP4Program(self._getMapMtzScriptFileName(), args="",
                       #extraEnvDict={'GENERIC': self._getExtraPath("")},
                       cwd=self._getExtraPath())

    def createRefineScriptFileStep(self):
        if self.generateMaskedVolume.get():
            data_refine = template_refmac_refine_MASK  % self.dict
        else:
            data_refine = template_refmac_refine_NOMASK % self.dict
        f_refine = open(self._getRefineScriptFileName(), "w")
        f_refine.write(data_refine)
        f_refine.close()
        os.chmod(self._getRefineScriptFileName(), stat.S_IEXEC | stat.S_IREAD |
                 stat.S_IWRITE)

    def executeRefineRefmacStep(self):
        # Generic is a env variable that coot uses as base dir for some
        # but not all files. "" force a trailing slash
        runCCP4Program(self._getRefineScriptFileName(), args = "",
                       #extraEnvDict = {'GENERIC': self._getExtraPath("")},
                       cwd=self._getExtraPath())

    def createRefmacOutputStep(self):
        pdb = PdbFile()
        pdb.setFileName(self._getOutPdbFileName(self.OutPdbFileName))
        self._defineOutputs(outputPdb=pdb)
        self._defineSourceRelation(self.inputStructure, self.outputPdb)
        fnVol = self._getInputVolume()
        self._defineSourceRelation(fnVol, self.outputPdb)

    def writeFinalResultsTableStep(self):
        with open(self._getlogFileName()) as input_data:
            for line in input_data:
                if line.strip() == '$TEXT:Result: $$ Final results $$':
                    break
            for line in input_data:
                if line.strip() == '$$':
                    break

    # --------------------------- UTLIS functions --------------------------

    def _validate(self):
        errors = []
        # Check that the program exists
        program = getProgram(self.REFMAC)
        if program is None:
            errors.append("Missing variables REFMAC and/or CCP4_HOME")
        elif not os.path.exists(program):
            errors.append("Binary '%s' does not exists.\n" % program)
        # If there is any error at this point it is related to config variables
        if errors:
            errors.append("Check configuration file: "
                          "~/.config/scipion/scipion.conf")
            errors.append("and set REFMAC and CCP4_HOME variables properly.")
            if program is not None:
                errors.append("Current values:")
                errors.append("CCP4_HOME = %s" % os.environ['CCP4_HOME'])
                errors.append("REFMAC = %s" % self.REFMAC)

        if not validVersion(7, 0.056):
            errors.append("CCP4 version should be at least 7.0.056")

        # Check that the input volume exist
        if self._getInputVolume() is None:
            errors.append("Error: You should provide a volume.\n")

        return errors

    def _getInputVolume(self):
        if self.inputVolume.get() is None:
            fnVol = self.inputStructure.get().getVolume()
        else:
            fnVol = self.inputVolume.get()
        return fnVol

    def _getOutPdbFileName(self, fileName=None):
        if fileName is None:
            fileName = self.OutPdbFileName
        return self._getExtraPath(fileName)

    def _getMapMtzScriptFileName(self):
        return os.path.abspath(self._getTmpPath(self.refmacMap2MtzScriptFileName))

    def _getRefineScriptFileName(self):
        return os.path.abspath(self._getTmpPath(self.refmacRefineScriptFileName))

    def _getlogFileName(self):
        return self._getExtraPath(self.refineLogFileName)

    def _getVolumeFileName(self, baseFileName="tmp3DMapFile.mrc"):
        return self._getExtraPath(baseFileName)

    def _citations(self):
        return ['Vagin_2004']

    def _summary(self):
        summary = []
        summary.append('refmac '
                       'keywords: '
                       'https://www2.mrc-lmb.cam.ac.uk/groups/murshudov'
                       '/content/refmac/refmac_keywords.html')
        return summary

    def _getMapMaskedByPdbBasedMaskFileName(self, baseFileName='mapMaskedByPdbBasedMask.mrc'):
        return baseFileName

    def _getPdbsetMaskPDBFileName(self, baseFileName='pdbset_mask.pdb'):
        return baseFileName

    def _getPdbsetNOMaskPDBFileName(self, baseFileName='pdbset.pdb'):
        return baseFileName
