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

        # Select modality for csv

        self.modalitySelector = qt.QComboBox()
        self.modalitySelector.addItems(["T2", "ADC", "DWI", "Lesion"])
        

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

        # Button to save segmentation as image (in English)
        self.saveSegmentationImageButton = qt.QPushButton("Save Segmentation as Image")
        self.layout.addWidget(self.saveSegmentationImageButton)
        self.saveSegmentationImageButton.connect('clicked(bool)', self.onSaveSegmentationImageButton)

        # Improve UI style
        # Group navigation buttons
        navLayout = qt.QHBoxLayout()
        navLayout.addWidget(self.previousButton)
        navLayout.addWidget(self.nextButton)
        navGroup = qt.QGroupBox("Image Navigation")
        navGroup.setLayout(navLayout)
        self.layout.addWidget(navGroup)

        # Group save button
        saveLayout = qt.QHBoxLayout()
        saveLayout.addWidget(self.saveSegmentationImageButton)
        saveGroup = qt.QGroupBox("Segmentation Saving")
        saveGroup.setLayout(saveLayout)
        self.layout.addWidget(saveGroup)

        # Style buttons
        button_style = """
            QPushButton {
                background-color: #1976d2;
                color: white;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """
        for btn in [self.loadCSVButton, self.nextButton, self.previousButton, self.saveSegmentationImageButton]:
            btn.setStyleSheet(button_style)
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(120)

        # Visual separator
        line = qt.QFrame()
        line.setFrameShape(qt.QFrame.HLine)
        line.setFrameShadow(qt.QFrame.Sunken)
        self.layout.addWidget(line)

        # Title for segment editor
        segmentLabel = qt.QLabel("Segment Editor")
        segmentLabel.setStyleSheet("font-weight: bold; font-size: 16px; margin-top: 10px;")
        self.layout.addWidget(segmentLabel)
        self.layout.addWidget(self.segmentEditorWidget)

        # Progress bar and label for segmentation progress
        self.progressLabel = qt.QLabel()
        self.progressLabel.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        self.progressBar = qt.QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)
        self.layout.addWidget(self.progressLabel)
        self.layout.addWidget(self.progressBar)

        self.linkSliceViews()
        self.imagePaths = []
        self.currentIndex = -1
        self.segmentedIndices = set()

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
            self.segmentedIndices = set()
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load CSV: {str(e)}")

    def onNextButton(self):
        """
        Handle the event when the 'Next' button is clicked.
        Loads the next set of images from the CSV file and marks the current as segmented.
        """
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        # Mark current as segmented if not already
        if 0 <= self.currentIndex < len(self.imagePaths):
            self.segmentedIndices.add(self.currentIndex)

        self.currentIndex += 1
        if self.currentIndex >= len(self.imagePaths):
            slicer.util.infoDisplay("No more images.")
            self.currentIndex = len(self.imagePaths) - 1
            return

        imagePaths = self.imagePaths[self.currentIndex]
        directoryPath = self.directoryPathEdit.text
        t2Path = os.path.join(directoryPath, imagePaths['T2'])
        adcPath = os.path.join(directoryPath, imagePaths['ADC'])
        dwiPath = os.path.join(directoryPath, imagePaths['DWI'])
        lesionPath = os.path.join(directoryPath, imagePaths.get('Lesion', ''))

        self.removePreviousImages()
        self.loadPatientImages(t2Path, adcPath, dwiPath, lesionPath)
        self.updateSegmentationProgress() 

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
        t2Path = os.path.join(directoryPath, imagePaths['T2'])
        adcPath = os.path.join(directoryPath, imagePaths['ADC'])
        dwiPath = os.path.join(directoryPath, imagePaths['DWI'])
        lesionPath = os.path.join(directoryPath, imagePaths.get('Lesion', ''))
        self.removePreviousImages()
        self.loadPatientImages(t2Path, adcPath, dwiPath, lesionPath)
        self.updateSegmentationProgress()

    def removePreviousImages(self):
        """
        Remove previously loaded images from the scene.
        """
        slicer.mrmlScene.Clear(0)

    def loadPatientImages(self, t2Path, adcPath, dwiPath, lesionPath):
        """
        Load patient images and segmentation from the specified paths.

        Parameters:
        - t2Path: Path to the T2-weighted image.
        - adcPath: Path to the ADC image.
        - dwiPath: Path to the DWI image.
        - lesionPath: Path to the lesion segmentation (optional).

        Raises:
        - Exception: If the images cannot be loaded.
        """
        try:
            t2Node = self.loadVolume(t2Path)
            adcNode = self.loadVolume(adcPath)
            dwiNode = self.loadVolume(dwiPath)
            
            if os.path.isfile(lesionPath):
                lesionNode = self.loadSegmentation(lesionPath, t2Node)
            else:
                slicer.util.infoDisplay("No Lesion Found for this Session.")
                lesionNode = None
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load images: {str(e)}")
            return

        self.resampleImagesToT2(t2Node, adcNode, dwiNode)
        self.setupSegmentEditor(t2Node, lesionNode)
        self.assignImagesToSliceViews(t2Node, adcNode, dwiNode)
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
        
        # Limpiar la segmentación existente antes de importar
        segmentation = segmentationNode.GetSegmentation()
        segmentation.RemoveAllSegments()

        # Actualizar el volumen de etiquetas con la imagen resampleada
        sitkUtils.PushVolumeToSlicer(resampledSegmentationImage, labelmapVolumeNode)

        # Importar el volumen de etiquetas resampleado a la segmentación
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
            labelmapVolumeNode, segmentationNode)
        
        # Eliminar el nodo de volumen de etiquetas temporal
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    

    def resampleImagesToT2(self, t2Node, adcNode, dwiNode):
        """
        Resample the ADC and DWI images to the T2-weighted image space.

        Parameters:
        - t2Node: The T2-weighted volume node.
        - adcNode: The ADC volume node.
        - dwiNode: The DWI volume node.
        """
        t2Image = sitkUtils.PullVolumeFromSlicer(t2Node)
        adcImage = sitkUtils.PullVolumeFromSlicer(adcNode)
        dwiImage = sitkUtils.PullVolumeFromSlicer(dwiNode)

        resampledAdcImage = self.resample_to_reference_scan(
            image=adcImage,
            reference_scan_original=t2Image
        )
        resampledDwiImage = self.resample_to_reference_scan(
            image=dwiImage,
            reference_scan_original=t2Image
        )

        sitkUtils.PushVolumeToSlicer(resampledAdcImage, adcNode)
        sitkUtils.PushVolumeToSlicer(resampledDwiImage, dwiNode)

    def assignImagesToSliceViews(self, t2Node, adcNode, dwiNode):
        """
        Assign the images to the slice views.

        Parameters:
        - t2Node: The T2-weighted volume node.
        - adcNode: The ADC volume node.
        - dwiNode: The DWI volume node.
        """
        lm = slicer.app.layoutManager()
        for sliceViewName, volumeNode in zip(['Red', 'Yellow', 'Green'], [t2Node, adcNode, dwiNode]):
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

    def save_segment_as_nii(self, segmentationNode, segment_name, output_path):
        """
        Guarda un segmento específico de un nodo de segmentación como archivo NIfTI (.nii.gz).
        """
        import sitkUtils
        # Crear un nodo temporal de segmentación solo con el segmento deseado
        temp_segmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        temp_segmentation.GetSegmentation().AddEmptySegment(segment_name)
        slicer.modules.segmentations.logic().CopySegmentFromSegmentationNode(
            segmentationNode, segment_name, temp_segmentation, segment_name)
        # Exportar a volumen de etiquetas
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(temp_segmentation, labelmapVolumeNode)
        # Guardar como NIfTI
        slicer.util.saveNode(labelmapVolumeNode, output_path)
        # Limpiar nodos temporales
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
        slicer.mrmlScene.RemoveNode(temp_segmentation)

    def onSaveSegmentationImageButton(self):
        """
        Guarda la segmentación actual como archivo NIfTI (.nii.gz) en la ubicación seleccionada.
        """
        # Obtener el nodo de segmentación actual
        segmentationNode = self.segmentEditorWidget.segmentationNode()
        if not segmentationNode:
            slicer.util.errorDisplay("No hay segmentación para guardar.")
            return

        # Verificar que hay al menos un segmento
        if segmentationNode.GetSegmentation().GetNumberOfSegments() == 0:
            slicer.util.errorDisplay("La segmentación no contiene ningún segmento.")
            return

        # Pedir al usuario que seleccione la ubicación y nombre del archivo
        output_path = qt.QFileDialog.getSaveFileName(
            self.parent, 
            "Guardar segmentación como NIfTI", 
            "", 
            "NIfTI Files (*.nii.gz);;NIfTI Files (*.nii)")

        if not output_path:
            return  # El usuario canceló

        # Asegurarse de que la extensión sea .nii.gz
        if not output_path.endswith('.nii.gz'):
            output_path += '.nii.gz'

        try:
            # Crear un volumen de etiquetas temporal
            labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")

            # Exportar todos los segmentos al nodo de volumen de etiquetas
            slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                segmentationNode, labelmapVolumeNode)

            # Guardar como NIfTI
            slicer.util.saveNode(labelmapVolumeNode, output_path)

            # Limpiar nodo temporal
            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

            slicer.util.infoDisplay(f"Segmentación guardada exitosamente en: {output_path}")
        except Exception as e:
            slicer.util.errorDisplay(f"Error al guardar la segmentación: {str(e)}")
            if labelmapVolumeNode:
                slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def updateSegmentationProgress(self):
        """
        Update the progress bar and label to show segmentation progress in the dataset.
        """
        total = len(self.imagePaths) if hasattr(self, 'imagePaths') else 0
        segmented = len(self.segmentedIndices) if hasattr(self, 'segmentedIndices') else 0
        if total > 0:
            self.progressBar.setMaximum(total)
            self.progressBar.setValue(segmented)
            self.progressLabel.setText(f"Segmentation progress: {segmented} of {total} images segmented")
        else:
            self.progressBar.setMaximum(1)
            self.progressBar.setValue(0)
            self.progressLabel.setText("Segmentation progress: 0 of 0 images segmented")