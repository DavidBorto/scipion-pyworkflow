# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
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
"""
This sub-package contains Spider protocol for PCA.
"""


from pyworkflow.em import *  
from pyworkflow.utils import removeExt, removeBaseExt, makePath, moveFile, copyFile, basename
import pyworkflow.utils.graph as graph
from constants import *
from spider import SpiderShell, SpiderDocFile, SpiderProtocol
from convert import locationToSpider
from glob import glob

      
# TODO: Remove from ProtAlign, and put in other category     
class SpiderProtClassifyWard(ProtClassify, SpiderProtocol):
    """ Ward's method, using 'CL HC' 
    """
    _label = 'ward'
    
    def __init__(self):
        ProtClassify.__init__(self)
        SpiderProtocol.__init__(self)
        
        self._params = {'ext': 'stk',
                        'particles': 'particles',
                        'particlesSel': 'particles_sel',
                        'dendroPs': 'dendrogram',
                        'dendroDoc': 'docdendro',
                        'averages': 'averages'
                        }
    
    #--------------------------- DEFINE param functions --------------------------------------------   
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputParticles', PointerParam, label="Input particles", important=True, 
                      pointerClass='SetOfParticles',
                      help='Input images to perform PCA')
        form.addParam('pcaFilePointer', PointerParam, pointerClass='PcaFile',
                      label="PCA file", 
                      help='IMC or SEQ file generated in CA-PCA')        
        form.addParam('numberOfFactors', IntParam, default=10,
                      label='Number of factors',
                      help='After running, examine the eigenimages and decide which ones to use.\n'
                           'Typically all but the first few are noisy.')
        form.addParam('numberOfLevels', IntParam, default=10, expertLevel=LEVEL_ADVANCED,
                      label='Number of levels',
                      help='When creating the set of classes, the classification tree.'
                           'whill be cut after this level.')
        
    #--------------------------- INSERT steps functions --------------------------------------------  
    def _insertAllSteps(self):
        pcaFile = self.pcaFilePointer.get().filename.get()
        
        self._insertFunctionStep('convertInput', 'inputParticles',
                                 self._getFileName('particles'), self._getFileName('particlesSel'))
        self._insertFunctionStep('classifyWardStep', pcaFile, self.numberOfFactors.get())
        self._insertFunctionStep('createOutputStep')
            
    #--------------------------- STEPS functions --------------------------------------------       
    def classifyWardStep(self, imcFile, numberOfFactors):
        """ Apply the selected filter to particles. 
        Create the set of particles.
        """
        self._params.update(locals()) # Store input params in dict
        
        # Copy file to working directory, it could be also a link
        imcLocalFile = basename(imcFile)
        copyFile(imcFile, self._getPath(imcLocalFile))
        print "copy from '%s' to '%s' " % (imcFile, imcLocalFile)
        imcLocalFile = removeExt(imcLocalFile)

        self._enterWorkingDir() # Do operations inside the run working dir

        spi = SpiderShell(ext=self._params['ext'], log='script.stk') # Create the Spider process to send commands 
        spi.runFunction('CL HC', imcLocalFile, '1-%d' % numberOfFactors, 0, 5, 
                        'Y', self._params['dendroPs'], 'Y', self._params['dendroDoc'])
        spi.close()
        
        self._leaveWorkingDir() # Go back to project dir
        
    def createOutputStep(self):
        rootNode = self.buildDendrogram(True)
        classes = self._createSetOfClasses2D(self.inputParticles.get())
        averages = classes.createAverages()
        g = graph.Graph(root=rootNode)  
            
        self._fillClassesFromNodes(classes, averages, g.getNodes())
        
        self._defineOutputs(outputClasses=classes)
         
    #--------------------------- INFO functions -------------------------------------------- 
    def _validate(self):
        errors = []
        return errors
    
    def _citations(self):
        cites = []
        return cites
    
    def _summary(self):
        summary = []
        return summary
    
    def _methods(self):
        return self._summary()  # summary is quite explicit and serve as methods
    
    #--------------------------- UTILS functions --------------------------------------------
    def _getFileName(self, key):
        #TODO: Move to a base Spider protocol
        template = '%(' + key + ')s.%(ext)s'
        return self._getPath(template % self._params)
      
    def _fillClassesFromNodes(self, classes, averages, nodeList):
        """ Create the SetOfClasses2D from the images of each node
        in the dendogram. 
        """
        img = Particle()
        sampling = classes.getSamplingRate()
        
        for node in nodeList:
            if node.path:
                #print "node.path: ", node.path
                class2D = Class2D()
                avg = Particle()
                #avg.copyObjId(class2D)
                avg.setLocation(node.avgCount, self.dendroAverages)
                avg.setSamplingRate(sampling)
                
                class2D.setAverage(avg)
                class2D.setSamplingRate(sampling)
                classes.append(class2D)
                #print "class2D.id: ", class2D.getObjId()
                for i in node.imageList:
                    #img.setObjId(i) # FIXME: this is wrong if the id is different from index
                    img.cleanObjId()
                    img.setLocation(int(i), self.dendroImages)
                    class2D.append(img)
                #averages.append(avg)
        
    def buildDendrogram(self, writeAverages=False):
        """ Parse Spider docfile with the information to build the dendogram.
        Params:
            dendroFile: docfile with a row per image. 
                 Each row contains the image id and the height.
        """ 
        dendroFile = self._getFileName('dendroDoc')
        # Dendrofile is a docfile with at least 3 data colums (class, height, id)
        doc = SpiderDocFile(dendroFile)
        values = []
        indexes = []
        for c, h, _ in doc.iterValues(): 
            indexes.append(c)
            values.append(h)
        doc.close()
        
        self.dendroValues = values
        self.dendroIndexes = indexes
        self.dendroImages = self._getFileName('particles')
        self.dendroAverages = self._getFileName('averages')
        self.dendroAverageCount = 0 # Write only the number of needed averages
        self.dendroMaxLevel = self.numberOfLevels.get()
        
        return self._buildDendrogram(0, len(values)-1, 1, writeAverages)
    
    def _buildDendrogram(self, leftIndex, rightIndex, index, writeAverages=False, level=0):
        """ This function is recursively called to create the dendogram graph(binary tree)
        and also to write the average image files.
        Params:
            leftIndex, rightIndex: the indinxes within the list where to search.
            index: the index of the class average.
            writeImages: flag to select when to write averages.
        From self:
            self.dendroValues: the list with the heights of each node
            self.dendroImages: image stack filename to read particles
            self.dendroAverages: stack name where to write averages
        It will search for the max in values list (between minIndex and maxIndex).
        Nodes to the left of the max are left childs and the other right childs.
        """
        maxValue = self.dendroValues[leftIndex]
        maxIndex = 0
        for i, v in enumerate(self.dendroValues[leftIndex+1:rightIndex]):
            if v > maxValue:
                maxValue = v
                maxIndex = i+1
        
        m = maxIndex + leftIndex
        node = DendroNode(index, maxValue)
        
        ih = ImageHandler()

        particleNumber = self.dendroIndexes[m+1]
        node.imageList = [particleNumber]
        
        if writeAverages:
            node.image = ih.read((particleNumber, self.dendroImages))
            
        def addChildNode(left, right, index):
            if right > left:
                child = self._buildDendrogram(left, right, index, writeAverages, level+1)
                node.addChild(child)
                node.length += child.length
                node.imageList += child.imageList
                
                if writeAverages:
                    node.image += child.image
                    del child.image # Allow to free child image memory
                
        if rightIndex > leftIndex + 1 and level < self.dendroMaxLevel:
            addChildNode(leftIndex, m, 2*index)
            addChildNode(m+1, rightIndex, 2*index+1)
            node.avgCount = self.dendroAverageCount + 1
            self.dendroAverageCount += 1
            node.path = '%d@%s' % (node.avgCount, self.dendroAverages)
            if writeAverages:
                #TODO: node['image'] /= float(node['length'])
                ih.write(node.image, (node.avgCount, self.dendroAverages))
                fn = self._getTmpPath('doc_class%03d.stk' % index)
                doc = SpiderDocFile(fn, 'w+')
                for i in node.imageList:
                    doc.writeValues(i)
                doc.close()
        return node
    

class DendroNode(graph.Node):
    """ Special type of Node to store dendogram values. """
    def __init__(self, index, height):
        graph.Node.__init__(self, 'class_%03d' % index)
        self.index = index
        self.height = height
        self.length = 1
        self.path = None
        self.selected = False
        
    def getChilds(self):
        return [c for c in self._childs if c.path]
    