#!/usr/bin/env python
# **************************************************************************
# *
# * Authors:    Airen Zaldivar         (airenzp@gmail.com)
#               J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
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

import sys
from pyworkflow.em import *
from pyworkflow.manager import Manager


if __name__ == '__main__':
    #TODO: REMOVE THIS AFTER DEBUGGING
    # print "ARGS: "
    # for i, arg in enumerate(sys.argv):
    #     print "%02d: %s" % (i, arg)
    projectId=sys.argv[1]
    inputId=sys.argv[2]
    file=sys.argv[3]

    project = Manager().loadProject(projectId)
    inputObject = project.mapper.selectById(int(inputId))

    prot = project.newProtocol(ProtImportMask, maskPath=file, samplingRate=inputObject.getSamplingRate())
    prot.setObjLabel('import mask')
    project.launchProtocol(prot)
