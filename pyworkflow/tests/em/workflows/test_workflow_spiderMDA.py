# **************************************************************************
# *
# * Authors:     J.M. de la Rosa Trevin (jmdelarosa@cnb.csic.es)
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
# *  e-mail address 'jgomez@cnb.csic.es'
# *
# **************************************************************************

from pyworkflow.em import (SpiderProtFilter, SpiderProtAlignAPSR, SpiderProtAlignPairwise,
                           SpiderProtCustomMask, SpiderProtCAPCA, SpiderProtClassifyWard, 
                           SpiderProtClassifyKmeans, SpiderProtClassifyDiday, ProtImportParticles,
                           )

from pyworkflow.tests import setupTestProject, DataSet, unittest
from test_workflow import TestWorkflow
   
   
       
class TestSpiderWorkflow(TestWorkflow):
    @classmethod
    def setUpClass(cls):    
        # Create a new project
        setupTestProject(cls)
        cls.dataset = DataSet.getDataSet('mda')
        cls.particlesFn = cls.dataset.getFile('particles')
    
    def test_mdaWorkflow(self):
        """ Run an Import particles protocol. """
        protImport = self.newProtocol(ProtImportParticles, pattern=self.particlesFn, samplingRate=3.5)
        self.launchProtocol(protImport)
        # check that input images have been imported (a better way to do this?)
        if protImport.outputParticles is None:
            raise Exception('Import of images: %s, failed. outputParticles is None.' % self.particlesFn)
        
        protFilter = self.newProtocol(SpiderProtFilter)
        protFilter.inputParticles.set(protImport)
        protFilter.inputParticles.setExtendedAttribute('outputParticles')
        self.launchProtocol(protFilter)
        
        protAPSR = self.newProtocol(SpiderProtAlignAPSR)
        protAPSR.inputParticles.set(protFilter.outputParticles)
        self.launchProtocol(protAPSR)
        
        protPairwise = self.newProtocol(SpiderProtAlignPairwise)
        protPairwise.inputParticles.set(protFilter.outputParticles)
        self.launchProtocol(protPairwise)       
         
        protMask = self.newProtocol(SpiderProtCustomMask)
        protMask.inputImage.set(protAPSR.outputAverage)
        self.launchProtocol(protMask)       
              
        protCAPCA = self.newProtocol(SpiderProtCAPCA)
        protCAPCA.maskType.set(1)
        protCAPCA.maskImage.set(protMask.outputMask)
        protCAPCA.inputParticles.set(protAPSR.outputParticles)
        self.launchProtocol(protCAPCA)
        
        protWard = self.newProtocol(SpiderProtClassifyWard)
        protWard.pcaFile.set(protCAPCA.imcFile)
        protWard.inputParticles.set(protAPSR.outputParticles)
        self.launchProtocol(protWard)
        
        protKmeans = self.newProtocol(SpiderProtClassifyKmeans)
        protKmeans.pcaFile.set(protCAPCA.imcFile)
        protKmeans.inputParticles.set(protAPSR.outputParticles)
        protKmeans.numberOfClasses.set(4)
        self.launchProtocol(protKmeans)
        
        protDiday = self.newProtocol(SpiderProtClassifyDiday)
        protDiday.pcaFile.set(protCAPCA.imcFile)
        protDiday.inputParticles.set(protAPSR.outputParticles)
        self.launchProtocol(protDiday)               
        


if __name__ == "__main__":
    unittest.main()
