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
        """
        Initialize the MRIAnnotator module.

        Parameters:
        - parent: The parent module.
        """
        parent.title = "Prostate MRI Annotator"
        parent.categories = ["Radiology"]
        parent.contributors = ["Jesús Alejandro Alzate-Grisales"]
        self.parent = parent

class MRIAnnotatorWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        """
        Set up the UI elements and initialize the widget.
        """
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
        """
        Handle the event when the 'Load CSV' button is clicked.
        Opens a file dialog to select a CSV file and loads it.
        """
        csvPath = qt.QFileDialog.getOpenFileName(self.parent, "Select CSV File", "", "CSV Files (*.csv)")
        if not csvPath:
            slicer.util.errorDisplay("CSV file not selected.")
            return

        self.loadCSV(csvPath)

    def loadCSV(self, csvPath):
        """
        Load image paths from the specified CSV file.

        Parameters:
        - csvPath: Path to the CSV file.

        Raises:
        - Exception: If the CSV file cannot be loaded.
        """
        try:
            with open(csvPath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                self.imagePaths = [row for row in reader]
            self.currentIndex = -1
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load CSV: {str(e)}")

    def onNextButton(self):
        """
        Handle the event when the 'Next' button is clicked.
        Loads the next set of images from the CSV file.
        """
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
        """
        Handle the event when the 'Previous' button is clicked.
        Loads the previous set of images from the CSV file.
        """
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
        """
        Remove previously loaded images from the scene.
        """
        slicer.mrmlScene.Clear(0)

    def loadPatientImages(self, t2wPath, adcPath, dwiPath, lesionPath):
        """
        Load patient images and segmentation from the specified paths.

        Parameters:
        - t2wPath: Path to the T2-weighted image.
        - adcPath: Path to the ADC image.
        - dwiPath: Path to the DWI image.
        - lesionPath: Path to the lesion segmentation (optional).

        Raises:
        - Exception: If the images cannot be loaded.
        """
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
        """
        Load a volume from the specified path.

        Parameters:
        - path: Path to the volume file.

        Returns:
        - The loaded volume node.

        Raises:
        - FileNotFoundError: If the file does not exist.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        return slicer.util.loadVolume(path)

    def loadSegmentation(self, path, referenceNode):
        """
        Load a segmentation from the specified path and resample it to the reference node.

        Parameters:
        - path: Path to the segmentation file.
        - referenceNode: The reference volume node.

        Returns:
        - The loaded segmentation node.

        Raises:
        - FileNotFoundError: If the file does not exist.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        segmentationNode = slicer.util.loadNodeFromFile(path, "SegmentationFile")
        self.resampleSegmentationToReference(segmentationNode, referenceNode)
        return segmentationNode

    def resample_to_reference_scan(
        self,
        image: Union[np.ndarray, sitk.Image],
        reference_scan_original: sitk.Image,
        reference_scan_preprocessed: Optional[sitk.Image] = None,
        interpolator: Optional[sitk.ResampleImageFilter] = None,
    ) -> sitk.Image:
        """
        Resample the image to the physical space of the original scan.

        Parameters:
        - image: Image, detection map, or (softmax) prediction.
        - reference_scan_original: SimpleITK image to which the prediction should be resampled and resized.
        - reference_scan_preprocessed: (Optional) SimpleITK image with physical metadata for `image`.
        - interpolator: (Optional) Interpolator to use for resampling.

        Returns:
        - The resampled image.

        Raises:
        - ValueError: If the image is not a SimpleITK image and no reference scan is provided.
        """
        # Convertir image a SimpleITK.Image y copiar metadatos físicos
        if not isinstance(image, sitk.Image):
            if reference_scan_preprocessed is None:
                raise ValueError("Se necesita una imagen SimpleITK o un escaneo de referencia para los metadatos físicos!")
            image = sitk.GetImageFromArray(image)

        if reference_scan_preprocessed is not None:
            image.CopyInformation(reference_scan_preprocessed)

        if interpolator is None:
            # Determinar el método de interpolación basado en el tipo de datos de la imagen
            dtype_name = image.GetPixelIDTypeAsString()
            if "integer" in dtype_name:
                interpolator = sitk.sitkNearestNeighbor
            elif "float" in dtype_name:
                interpolator = sitk.sitkLinear
            else:
                raise ValueError(f"Tipo de píxel desconocido {dtype_name}")

        # Preparar el resampling al escaneo original
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(reference_scan_original)
        resampler.SetInterpolator(interpolator)

        # Resamplear la imagen al escaneo original
        image = resampler.Execute(image)

        return image

    def resampleSegmentationToReference(self, segmentationNode, referenceNode):
        """
        Resample the segmentation to the reference node.

        Parameters:
        - segmentationNode: The segmentation node to resample.
        - referenceNode: The reference volume node.
        """
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
        resampledSegmentationImage = self.resample_to_reference_scan(
            image=segmentationImage,
            reference_scan_original=referenceImage,
            interpolator=sitk.sitkNearestNeighbor
        )
        
        # Actualizar el volumen de etiquetas con la imagen resampleada
        sitkUtils.PushVolumeToSlicer(resampledSegmentationImage, labelmapVolumeNode)
        
        # Importar el volumen de etiquetas resampleado a la segmentación
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
            labelmapVolumeNode, segmentationNode)
        
        # Eliminar el nodo de volumen de etiquetas temporal
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    

    def resampleImagesToT2w(self, t2wNode, adcNode, dwiNode):
        """
        Resample the ADC and DWI images to the T2-weighted image space.

        Parameters:
        - t2wNode: The T2-weighted volume node.
        - adcNode: The ADC volume node.
        - dwiNode: The DWI volume node.
        """
        t2wImage = sitkUtils.PullVolumeFromSlicer(t2wNode)
        adcImage = sitkUtils.PullVolumeFromSlicer(adcNode)
        dwiImage = sitkUtils.PullVolumeFromSlicer(dwiNode)

        resampledAdcImage = self.resample_to_reference_scan(
            image=adcImage,
            reference_scan_original=t2wImage
        )
        resampledDwiImage = self.resample_to_reference_scan(
            image=dwiImage,
            reference_scan_original=t2wImage
        )

        sitkUtils.PushVolumeToSlicer(resampledAdcImage, adcNode)
        sitkUtils.PushVolumeToSlicer(resampledDwiImage, dwiNode)

    def assignImagesToSliceViews(self, t2wNode, adcNode, dwiNode):
        """
        Assign the images to the slice views.

        Parameters:
        - t2wNode: The T2-weighted volume node.
        - adcNode: The ADC volume node.
        - dwiNode: The DWI volume node.
        """
        lm = slicer.app.layoutManager()
        for sliceViewName, volumeNode in zip(['Red', 'Yellow', 'Green'], [t2wNode, adcNode, dwiNode]):
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
            sliceCompositeNode.SetBackgroundVolumeID(volumeNode.GetID())
            sliceWidget.mrmlSliceNode().SetOrientationToAxial()
            sliceWidget.sliceController().setSliceLink(True)
            sliceWidget.sliceLogic().FitSliceToAll()

    def setupSegmentEditor(self, masterVolumeNode, segmentationNode):
        """
        Set up the segment editor with the specified master volume and segmentation nodes.

        Parameters:
        - masterVolumeNode: The master volume node.
        - segmentationNode: The segmentation node.
        """
        segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        self.segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
        
        if segmentationNode is None:
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            segmentationNode.SetName("Segmentation")
        self.segmentEditorWidget.setSegmentationNode(segmentationNode)
        self.segmentEditorWidget.setSourceVolumeNode(masterVolumeNode)

    def linkSliceViews(self):
        """
        Link the slice views and set their orientation to axial.
        """
        lm = slicer.app.layoutManager()
        for sliceViewName in ['Red', 'Yellow', 'Green']:
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceWidget.sliceController().setSliceLink(True)
            sliceWidget.mrmlSliceNode().SetOrientationToAxial()
            sliceWidget.sliceLogic().FitSliceToAll()