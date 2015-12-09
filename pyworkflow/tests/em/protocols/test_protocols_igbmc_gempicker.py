# **************************************************************************
# *
# * Authors:    Grigory Sharov (sharov@igbmc.fr)
# *             J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
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
# *  e-mail address 'jmdelarosa@cnb.csic.es'
# *
# **************************************************************************

import unittest, sys
from os.path import join, basename

from pyworkflow.em import *
from pyworkflow.tests import *
from pyworkflow.em.packages.igbmc.protocol_gempicker import *

import pyworkflow.utils as pwutils



class TestIgbmcBase(BaseTest):
    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('igbmc_gempicker')
    
    @classmethod
    def runImportAverages(cls):
        """ Run an Import averages protocol. """
        cls.protImportAvg = cls.newProtocol(ProtImportAverages, 
                                            objLabel='import averages (klh)',
                                            filesPath=cls.ds.getFile('templates/*.mrc'), 
                                            samplingRate=4.4)

        cls.launchProtocol(cls.protImportAvg)
        return cls.protImportAvg
 
    @classmethod
    def runImportMask(cls):
        """ Run an Import mask protocol. """
        cls.protImportMsk = cls.newProtocol(ProtImportMask, 
                                          objLabel='import mask (klh)',
                                          maskPath=cls.ds.getFile('masks/mask.tif'), 
                                          samplingRate=4.4)

        cls.launchProtocol(cls.protImportMsk)
        return cls.protImportMsk

    @classmethod
    def runImportMicrograph(cls, pattern, samplingRate, voltage, magnification, sphericalAberration):
        """ Run an Import micrograph protocol. """
        cls.protImport = cls.newProtocol(ProtImportMicrographs,
                                         objLabel='import mics (klh)', 
                                         samplingRateMode=0, 
                                         filesPath=pattern, 
                                         samplingRate=samplingRate, 
                                         magnification=magnification, 
                                         voltage=voltage, 
                                         sphericalAberration=sphericalAberration)
            
        cls.launchProtocol(cls.protImport)
        return cls.protImport
    
    @classmethod
    def runImportMicrographKLH(cls):
        """ Run an Import micrograph protocol. """
        return cls.runImportMicrograph(cls.ds.getFile('micrographs/*.mrc'), 
                                       samplingRate=2.2, 
                                       voltage=120, sphericalAberration=2,
                                       magnification=66000)
    
    @classmethod
    def runPicking(cls):
        """ Run a particle picking. """
        protGP = ProtGemPicker(refsHaveInvertedContrast=True,
                               maskType=MASK_CIRCULAR,
                               useGPU=False)                
        protGP.inputMicrographs.set(cls.protImportMics.outputMicrographs)
        protGP.inputReferences.set(cls.protImportAvgs.outputAverages)
        cls.launchProtocol(protGP)
        return protGP


class TestGempickerAutomaticPicking(TestIgbmcBase):
    """This class check if the protocol to pick the micrographs automatically by gempicker works properly."""
    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        TestIgbmcBase.setData()
        cls.protImportMics = cls.runImportMicrographKLH()
        cls.protImportMask = cls.runImportMask()
        cls.protImportAvgs = cls.runImportAverages()
    
    def testAutomaticPicking(self):
        print "Run automatic particle picking"
        self.runPicking()
