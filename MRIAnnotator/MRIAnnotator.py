import os
import slicer
from slicer.ScriptedLoadableModule import *
import qt
import SimpleITK as sitk
import sitkUtils
import numpy as np
import csv
from typing import Iterable, Optional, Union


class MRIAnnotator(ScriptedLoadableModule):
    def __init__(self, parent):
        parent.title = "Prostate MRI Annotator"
        parent.categories = ["Radiology"]
        parent.contributors = ["Jesús Alejandro Alzate-Grisales"]
        self.parent = parent

class MRIAnnotatorWidget(ScriptedLoadableModuleWidget):
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

        # Directory path input
        self.directoryPathEdit = qt.QLineEdit()
        self.directoryPathEdit.setPlaceholderText("Enter directory path")
        self.layout.addWidget(self.directoryPathEdit)

        # Button to load CSV
        self.loadCSVButton = qt.QPushButton("Load CSV")
        self.layout.addWidget(self.loadCSVButton)
        self.loadCSVButton.connect('clicked(bool)', self.onLoadCSVButton)

        # Button to load next images
        self.nextButton = qt.QPushButton("Next")
        self.layout.addWidget(self.nextButton)
        self.nextButton.connect('clicked(bool)', self.onNextButton)

        # Button to load previous images
        self.previousButton = qt.QPushButton("Previous")
        self.layout.addWidget(self.previousButton)
        self.previousButton.connect('clicked(bool)', self.onPreviousButton)

        # Segment editor widget
        self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.layout.addWidget(self.segmentEditorWidget)

        self.linkSliceViews()
        self.imagePaths = []
        self.currentIndex = -1

    def onLoadCSVButton(self):
        csvPath = qt.QFileDialog.getOpenFileName(self.parent, "Select CSV File", "", "CSV Files (*.csv)")
        if not csvPath:
            slicer.util.errorDisplay("CSV file not selected.")
            return

        self.loadCSV(csvPath)

    def loadCSV(self, csvPath):
        try:
            with open(csvPath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                self.imagePaths = [row for row in reader]
            self.currentIndex = -1
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load CSV: {str(e)}")

    def onNextButton(self):
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        self.currentIndex += 1
        if self.currentIndex >= len(self.imagePaths):
            slicer.util.infoDisplay("No more images.")
            self.currentIndex = len(self.imagePaths) - 1
            return

        imagePaths = self.imagePaths[self.currentIndex]
        directoryPath = self.directoryPathEdit.text
        t2wPath = os.path.join(directoryPath, imagePaths['T2w'])
        adcPath = os.path.join(directoryPath, imagePaths['ADC'])
        dwiPath = os.path.join(directoryPath, imagePaths['DWI'])
        lesionPath = os.path.join(directoryPath, imagePaths.get('Lesion', ''))

        self.removePreviousImages()
        self.loadPatientImages(t2wPath, adcPath, dwiPath, lesionPath)

    def onPreviousButton(self):
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        self.currentIndex -= 1
        if self.currentIndex < 0:
            slicer.util.infoDisplay("No previous images.")
            self.currentIndex = 0
            return

        imagePaths = self.imagePaths[self.currentIndex]
        directoryPath = self.directoryPathEdit.text
        t2wPath = os.path.join(directoryPath, imagePaths['T2w'])
        adcPath = os.path.join(directoryPath, imagePaths['ADC'])
        dwiPath = os.path.join(directoryPath, imagePaths['DWI'])
        lesionPath = os.path.join(directoryPath, imagePaths.get('Lesion', ''))
        self.removePreviousImages()
        self.loadPatientImages(t2wPath, adcPath, dwiPath, lesionPath)

    def removePreviousImages(self):
        slicer.mrmlScene.Clear(0)

    def loadPatientImages(self, t2wPath, adcPath, dwiPath, lesionPath):
        try:
            t2wNode = self.loadVolume(t2wPath)
            adcNode = self.loadVolume(adcPath)
            dwiNode = self.loadVolume(dwiPath)
            if os.path.isfile(lesionPath):
                lesionNode = self.loadSegmentation(lesionPath, t2wNode)
            else:
                slicer.util.infoDisplay("No Lesion Found for this Session.")
                lesionNode = None
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load images: {str(e)}")
            return

        self.resampleImagesToT2w(t2wNode, adcNode, dwiNode)
        self.setupSegmentEditor(t2wNode, lesionNode)
        self.assignImagesToSliceViews(t2wNode, adcNode, dwiNode)
        #self.linkSliceViews()
        #slicer.app.applicationLogic().FitSliceToAll()

    def loadVolume(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        return slicer.util.loadVolume(path)

    def loadSegmentation(self, path, referenceNode):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        segmentationNode = slicer.util.loadNodeFromFile(path, "SegmentationFile")
        self.resampleSegmentationToReference(segmentationNode, referenceNode)
        return segmentationNode

    def resampleSegmentationToReference(self, segmentationNode, referenceNode):
        # Establecer la geometría de referencia en el nodo de segmentación
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(referenceNode)
        
        # Crear un volumen de etiquetas temporal
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        
        # Exportar todos los segmentos al nodo de volumen de etiquetas
        slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
            segmentationNode, labelmapVolumeNode,0)
        
        # Obtener las imágenes en SimpleITK
        referenceImage = sitkUtils.PullVolumeFromSlicer(referenceNode)
        segmentationImage = sitkUtils.PullVolumeFromSlicer(labelmapVolumeNode)
        
        # Resamplear el volumen de etiquetas
        resampledSegmentationImage = self.resample_img(
            segmentationImage, reference_image=referenceImage, is_label=True)
        
        # Actualizar el volumen de etiquetas con la imagen resampleada
        sitkUtils.PushVolumeToSlicer(resampledSegmentationImage, labelmapVolumeNode)
        
        # Importar el volumen de etiquetas resampleado a la segmentación
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
            labelmapVolumeNode, segmentationNode)
        
        # Eliminar el nodo de volumen de etiquetas temporal
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def resample_img(
        self,
        image: sitk.Image,
        reference_image: sitk.Image,
        is_label: bool = False,
        pad_value: Optional[Union[float, int]] = 0.,
    ) -> sitk.Image:
        """
        Resample images to target resolution spacing and size
        Ref: SimpleITK
        """
        # get reference spacing and size
        out_spacing = reference_image.GetSpacing()
        out_size = reference_image.GetSize()

        # determine pad value
        if pad_value is None:
            pad_value = image.GetPixelIDValue()

        # set up resampler
        resample = sitk.ResampleImageFilter()
        resample.SetOutputSpacing(out_spacing)
        resample.SetSize(out_size)
        resample.SetOutputDirection(reference_image.GetDirection())
        resample.SetOutputOrigin(reference_image.GetOrigin())
        resample.SetTransform(sitk.Transform())
        resample.SetDefaultPixelValue(pad_value)
        if is_label:
            resample.SetInterpolator(sitk.sitkNearestNeighbor)
        else:
            resample.SetInterpolator(sitk.sitkBSpline)

        # perform resampling
        image = resample.Execute(image)

        return image

    def resampleImagesToT2w(self, t2wNode, adcNode, dwiNode):
        t2wImage = sitkUtils.PullVolumeFromSlicer(t2wNode)
        adcImage = sitkUtils.PullVolumeFromSlicer(adcNode)
        dwiImage = sitkUtils.PullVolumeFromSlicer(dwiNode)

        resampledAdcImage = self.resample_img(adcImage, reference_image=t2wImage)
        resampledDwiImage = self.resample_img(dwiImage, reference_image=t2wImage)

        sitkUtils.PushVolumeToSlicer(resampledAdcImage, adcNode)
        sitkUtils.PushVolumeToSlicer(resampledDwiImage, dwiNode)

    def assignImagesToSliceViews(self, t2wNode, adcNode, dwiNode):
        lm = slicer.app.layoutManager()
        for sliceViewName, volumeNode in zip(['Red', 'Yellow', 'Green'], [t2wNode, adcNode, dwiNode]):
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
            sliceCompositeNode.SetBackgroundVolumeID(volumeNode.GetID())
            sliceWidget.mrmlSliceNode().SetOrientationToAxial()
            sliceWidget.sliceController().setSliceLink(True)
            sliceWidget.sliceLogic().FitSliceToAll()

    def setupSegmentEditor(self, masterVolumeNode, segmentationNode):
        segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        self.segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
        
        if segmentationNode is None:
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            segmentationNode.SetName("Segmentation")
        self.segmentEditorWidget.setSegmentationNode(segmentationNode)
        self.segmentEditorWidget.setSourceVolumeNode(masterVolumeNode)

    def linkSliceViews(self):
        lm = slicer.app.layoutManager()
        for sliceViewName in ['Red', 'Yellow', 'Green']:
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceWidget.sliceController().setSliceLink(True)
            sliceWidget.mrmlSliceNode().SetOrientationToAxial()
            sliceWidget.sliceLogic().FitSliceToAll()