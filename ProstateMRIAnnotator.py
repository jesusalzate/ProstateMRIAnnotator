import os
import slicer
from slicer.ScriptedLoadableModule import *

class ProstateMRIViewer(ScriptedLoadableModule):
    def __init__(self, parent):
        parent.title = "Prostate MRI Viewer"
        parent.categories = ["Radiology"]
        parent.contributors = ["Your Name"]
        self.parent = parent

class ProstateMRIViewerWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        
        # UI elements for patient selection
        self.patientSelector = slicer.qMRMLNodeComboBox()
        self.patientSelector.nodeTypes = ["vtkMRMLFolderDisplayNode"]
        self.patientSelector.selectNodeUponCreation = True
        self.patientSelector.addEnabled = False
        self.patientSelector.removeEnabled = False
        self.patientSelector.noneEnabled = False
        self.patientSelector.showHidden = False
        self.patientSelector.setMRMLScene(slicer.mrmlScene)
        self.layout.addWidget(self.patientSelector)

        # Button to load images
        self.loadButton = qt.QPushButton("Load Patient Images")
        self.layout.addWidget(self.loadButton)
        self.loadButton.connect('clicked(bool)', self.onLoadButton)

        # Set up the MONAI Label segment editor widget if needed

    def onLoadButton(self):
        patientID = self.patientSelector.currentNode().GetName()
        self.loadPatientImages(patientID)

    def loadPatientImages(self, patientID):
        # Define paths to the images
        basePath = f"/path/to/your/data/{patientID}"
        t2wPath = os.path.join(basePath, "T2w.nii.gz")
        adcPath = os.path.join(basePath, "ADC.nii.gz")
        dwiPath = os.path.join(basePath, "DWI.nii.gz")

        # Load images
        t2wNode = slicer.util.loadVolume(t2wPath, returnNode=True)[1]
        adcNode = slicer.util.loadVolume(adcPath, returnNode=True)[1]
        dwiNode = slicer.util.loadVolume(dwiPath, returnNode=True)[1]

        # Assign images to slice views
        lm = slicer.app.layoutManager()
        lm.sliceWidget('Red').mrmlSliceCompositeNode().SetBackgroundVolumeID(t2wNode.GetID())
        lm.sliceWidget('Yellow').mrmlSliceCompositeNode().SetBackgroundVolumeID(adcNode.GetID())
        lm.sliceWidget('Green').mrmlSliceCompositeNode().SetBackgroundVolumeID(dwiNode.GetID())

        # Link slice views
        for sliceViewName in ['Red', 'Yellow', 'Green']:
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceWidget.sliceController().setSliceLink(True)

        # Reset slice views to fit the images
        slicer.app.applicationLogic().FitSliceToAll()

        # Optionally, initiate MONAI Label segmentation

