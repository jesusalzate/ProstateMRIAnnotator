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

        # Directory path input
        self.directoryPathEdit = qt.QLineEdit()
        self.directoryPathEdit.setPlaceholderText("Enter directory path")
        
        # Button to browse directory
        self.browseDirectoryButton = qt.QPushButton("Browse Directory")
        self.browseDirectoryButton.connect('clicked(bool)', self.onBrowseDirectoryButton)
        
        # Layout for directory selection
        directoryLayout = qt.QHBoxLayout()
        directoryLayout.addWidget(self.directoryPathEdit)
        directoryLayout.addWidget(self.browseDirectoryButton)
        directoryGroup = qt.QGroupBox("Root Directory")
        directoryGroup.setLayout(directoryLayout)
        self.layout.addWidget(directoryGroup)

        # Button to load CSV
        self.loadCSVButton = qt.QPushButton("Load CSV")
        
        # Layout for CSV loading
        csvLayout = qt.QHBoxLayout()
        csvLayout.addWidget(self.loadCSVButton)
        csvGroup = qt.QGroupBox("CSV Selection")
        csvGroup.setLayout(csvLayout)
        self.layout.addWidget(csvGroup)
        
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

        # Button to save segmentation as image (in English)
        self.saveSegmentationImageButton = qt.QPushButton("Save Segmentation as Image")
        self.layout.addWidget(self.saveSegmentationImageButton)
        self.saveSegmentationImageButton.connect('clicked(bool)', self.onSaveSegmentationImageButton)

        # Button to select segmentation modality
        self.selectSegmentationModalityButton = qt.QPushButton("Select Segmentation Modality")
        self.selectSegmentationModalityButton.setToolTip("Choose the modality column for saving segmentations.")
        self.selectSegmentationModalityButton.clicked.connect(self.onSelectSegmentationModality)
        self.layout.addWidget(self.selectSegmentationModalityButton)
        self.selectedSegmentationModality = None

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
        for btn in [self.loadCSVButton, self.browseDirectoryButton, self.nextButton, self.previousButton, self.saveSegmentationImageButton]:
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
        # Initialize tracking of loaded nodes for safe removal
        self.loadedVolumeNodes = []
        self.loadedSegmentationNode = None
        self.segmentEditorNode = None
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
            
            # Auto-select the first tumor modality if none is selected
            if self.imagePaths and (not hasattr(self, 'selectedSegmentationModality') or self.selectedSegmentationModality is None):
                columns = list(self.imagePaths[0].keys())
                tumor_columns = [col for col in columns if isinstance(col, str) and 'tumor' in col.lower()]
                if tumor_columns:
                    self.selectedSegmentationModality = tumor_columns[0]
                    print(f"Auto-selected segmentation modality: {self.selectedSegmentationModality}")
                    slicer.util.infoDisplay(f"Auto-selected segmentation modality: {self.selectedSegmentationModality}")
                else:
                    self.selectedSegmentationModality = None
                    print("No tumor columns found in CSV")
                    
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load CSV: {str(e)}")

    def onBrowseDirectoryButton(self):
        """
        Handle the event when the 'Browse Directory' button is clicked.
        Opens a file dialog to select a root directory and sets it in the text field.
        """
        try:
            # Get current directory from text field or use home directory as default
            currentDir = self.directoryPathEdit.text if self.directoryPathEdit.text else os.path.expanduser("~")
            
            directoryPath = qt.QFileDialog.getExistingDirectory(
                self.parent, 
                "Select Root Directory for Images", 
                currentDir
            )
            
            if directoryPath:
                self.directoryPathEdit.setText(directoryPath)
                print(f"Root directory set to: {directoryPath}")  # Debug print
                slicer.util.infoDisplay(f"Root directory set to: {directoryPath}")
            else:
                print("No directory selected")  # Debug print
                
        except Exception as e:
            error_msg = f"Error selecting directory: {str(e)}"
            print(error_msg)  # Debug print
            slicer.util.errorDisplay(error_msg)

    def onNextButton(self):
        """
        Handle the event when the 'Next' button is clicked.
        Loads the next set of images from the CSV file and marks the current as segmented.
        """
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        # Save current segmentation before moving to next
        if 0 <= self.currentIndex < len(self.imagePaths):
            self.saveCurrentSegmentationForCurrentRow()
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
        # Usar la modalidad seleccionada para la segmentación
        lesion_col = self.selectedSegmentationModality if hasattr(self, 'selectedSegmentationModality') and self.selectedSegmentationModality else 'Lesion'
        lesionPath = os.path.join(directoryPath, imagePaths.get(lesion_col, ''))
        
        # Debug prints
        print(f"Selected segmentation modality: {lesion_col}")
        print(f"Lesion path: {lesionPath}")
        print(f"Available columns: {list(imagePaths.keys())}")

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
        # Usar la modalidad seleccionada para la segmentación
        lesion_col = self.selectedSegmentationModality if hasattr(self, 'selectedSegmentationModality') and self.selectedSegmentationModality else 'Lesion'
        lesionPath = os.path.join(directoryPath, imagePaths.get(lesion_col, ''))
        
        # Debug prints
        print(f"Selected segmentation modality: {lesion_col}")
        print(f"Lesion path: {lesionPath}")
        print(f"Available columns: {list(imagePaths.keys())}")
        
        self.removePreviousImages()
        self.loadPatientImages(t2Path, adcPath, dwiPath, lesionPath)
        self.updateSegmentationProgress()

    def removePreviousImages(self):
        """
        Safely remove previously loaded images, segmentations, and editor nodes.
        """
        # Remove only tracked volume nodes
        for node in getattr(self, 'loadedVolumeNodes', []):
            if node and slicer.mrmlScene.GetNodeByID(node.GetID()):
                slicer.mrmlScene.RemoveNode(node)
        self.loadedVolumeNodes = []
        # Remove loaded segmentation if any
        if getattr(self, 'loadedSegmentationNode', None):
            node = self.loadedSegmentationNode
            if slicer.mrmlScene.GetNodeByID(node.GetID()):
                slicer.mrmlScene.RemoveNode(node)
            self.loadedSegmentationNode = None
        # Remove segment editor node
        if getattr(self, 'segmentEditorNode', None):
            node = self.segmentEditorNode
            if slicer.mrmlScene.GetNodeByID(node.GetID()):
                slicer.mrmlScene.RemoveNode(node)
            self.segmentEditorNode = None

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
            # Load volumes and optional lesion segmentation
            t2Node = self.loadVolume(t2Path)
            adcNode = self.loadVolume(adcPath)
            dwiNode = self.loadVolume(dwiPath)
            if os.path.isfile(lesionPath):
                lesionNode = self.loadSegmentation(lesionPath, t2Node)
            else:
                slicer.util.infoDisplay("No Lesion Found for this Session.")
                lesionNode = None
            # Track loaded nodes for removal
            self.loadedVolumeNodes = [t2Node, adcNode, dwiNode]
            self.loadedSegmentationNode = lesionNode
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
        # Track segment editor node for cleanup
        self.segmentEditorNode = segmentEditorNode
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

    def onSelectSegmentationModality(self):
        """
        Show a dialog to select the tumor modality column for saving segmentations.
        Only columns containing 'tumor' (case-insensitive) are shown.
        """
        if not hasattr(self, 'imagePaths') or not self.imagePaths:
            slicer.util.errorDisplay("Load a CSV first.")
            return
        columns = list(self.imagePaths[0].keys())
        print(f"All columns: {columns}")
        # Filtrar solo columnas que sean str y contengan 'tumor' (insensible a mayúsculas/minúsculas)
        tumor_columns = [col for col in columns if isinstance(col, str) and 'tumor' in col.lower()]
        print(f"Tumor columns found: {tumor_columns}")
        if not tumor_columns:
            slicer.util.errorDisplay("No tumor modalities found in CSV columns.")
            return
        item, ok = qt.QInputDialog.getItem(self.parent, "Select Tumor Segmentation Modality", "Tumor Modality:", tumor_columns, 0, False)
        if ok and item:
            self.selectedSegmentationModality = item
            print(f"User selected modality: {item}")
            slicer.util.infoDisplay(f"Segmentation modality set to: {item}")
        else:
            slicer.util.infoDisplay("No modality selected. Using default.")
        # Set default if not set
        if not self.selectedSegmentationModality:
            self.selectedSegmentationModality = tumor_columns[0]
            print(f"Set default modality: {self.selectedSegmentationModality}")

    def saveCurrentSegmentationForCurrentRow(self):
        """
        Save the current segmentation in the selected modality for the current row.
        If no segmentation, create empty.nii.gz. If empty exists and segmentation is created, replace it.
        """
        if not hasattr(self, 'imagePaths') or self.currentIndex < 0 or self.currentIndex >= len(self.imagePaths):
            return
            
        try:
            row = self.imagePaths[self.currentIndex]
            id_actual = row.get('ID', str(self.currentIndex+1).zfill(3))
            directoryPath = self.directoryPathEdit.text
            
            if not directoryPath:
                print("No directory path set")
                return
                
            # Folder for this case
            case_folder = os.path.join(directoryPath, f"{id_actual}_done")
            if not os.path.exists(case_folder):
                os.makedirs(case_folder)
                
            # File name for segmentation
            modality = self.selectedSegmentationModality or list(row.keys())[0]
            seg_filename = os.path.join(case_folder, f"{modality}.nii.gz")
            empty_filename = os.path.join(case_folder, "empty.nii.gz")
            
            print(f"Attempting to save segmentation for modality: {modality}")
            
            segmentationNode = self.segmentEditorWidget.segmentationNode()
            
            # Check if segmentation exists and has segments
            if not segmentationNode:
                print("No segmentation node found")
                self._createEmptyFile(empty_filename)
                return
                
            segmentation = segmentationNode.GetSegmentation()
            if not segmentation or segmentation.GetNumberOfSegments() == 0:
                print("No segments found in segmentation")
                self._createEmptyFile(empty_filename)
                return
                
            print(f"Found segmentation with {segmentation.GetNumberOfSegments()} segments")
            
            # Remove empty file if it exists
            if os.path.exists(empty_filename):
                try:
                    os.remove(empty_filename)
                    print("Removed empty.nii.gz file")
                except Exception as e:
                    print(f"Warning: Could not remove empty file: {e}")
            
            # Use labelmap method only - more stable for .nii.gz format
            print("Using labelmap method for .nii.gz save")
            self._saveThroughLabelmap(segmentationNode, seg_filename, id_actual)
                        
        except Exception as e:
            print(f"General error in saveCurrentSegmentationForCurrentRow: {str(e)}")
            slicer.util.errorDisplay(f"Error saving segmentation: {str(e)}")
    
    def _createEmptyFile(self, empty_filename):
        """Helper to create empty file safely"""
        if not os.path.exists(empty_filename):
            try:
                with open(empty_filename, 'wb') as f:
                    pass
                print(f"Created empty file: {empty_filename}")
                slicer.util.infoDisplay(f"No segmentation found. Created empty file: {empty_filename}")
            except Exception as empty_error:
                print(f"Error creating empty file: {str(empty_error)}")
                slicer.util.errorDisplay(f"Error creating empty file: {str(empty_error)}")
    
    def _saveThroughLabelmap(self, segmentationNode, seg_filename, id_actual):
        """Helper to save segmentation through labelmap method"""
        import time
        labelmapVolumeNode = None
        try:
            print("Starting labelmap save process...")
            
            # Create labelmap node with unique name
            timestamp = str(int(time.time() * 1000))  # millisecond timestamp
            labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            labelmapVolumeNode.SetName(f"TempLabelmap_{id_actual}_{timestamp}")
            
            print(f"Created temporary labelmap node: {labelmapVolumeNode.GetName()}")
            
            # Process events and wait
            slicer.app.processEvents()
            time.sleep(0.2)  # Increased delay
            
            # Export segments to labelmap with error checking
            print("Exporting segments to labelmap...")
            logic = slicer.modules.segmentations.logic()
            
            # Verify segmentation node is valid before export
            if not segmentationNode or not segmentationNode.GetSegmentation():
                raise Exception("Invalid segmentation node")
                
            # Set reference geometry if not set
            masterVolumeNode = self.segmentEditorWidget.sourceVolumeNode()
            if masterVolumeNode:
                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(masterVolumeNode)
                print("Set reference geometry from master volume")
            
            # Export with error checking
            result = logic.ExportAllSegmentsToLabelmapNode(segmentationNode, labelmapVolumeNode)
            if not result:
                raise Exception("ExportAllSegmentsToLabelmapNode failed")
            
            print("Export completed successfully")
            
            # Process events and wait
            slicer.app.processEvents()
            time.sleep(0.2)  # Increased delay
            
            # Verify the labelmap was created properly
            imageData = labelmapVolumeNode.GetImageData()
            if imageData is None:
                raise Exception("Labelmap creation failed - no image data")
            
            print(f"Labelmap created with dimensions: {imageData.GetDimensions()}")
            
            # Save the labelmap with full path verification
            print(f"Saving labelmap to: {seg_filename}")
            
            # Ensure directory exists
            import os
            os.makedirs(os.path.dirname(seg_filename), exist_ok=True)
            
            # Use more specific save method for NIfTI
            success = slicer.util.saveNode(labelmapVolumeNode, seg_filename, 
                                         {"useCompression": True})
            
            if success:
                # Verify file was actually created
                if os.path.exists(seg_filename):
                    file_size = os.path.getsize(seg_filename)
                    print(f"Segmentation saved successfully: {seg_filename} ({file_size} bytes)")
                    slicer.util.infoDisplay(f"Segmentation saved: {seg_filename}")
                else:
                    raise Exception("File was not created despite success flag")
            else:
                raise Exception("saveNode returned False")
                
        except Exception as labelmap_error:
            print(f"Error during labelmap save: {str(labelmap_error)}")
            slicer.util.errorDisplay(f"Error saving segmentation: {str(labelmap_error)}")
            
        finally:
            # Clean up temporary node with maximum safety
            if labelmapVolumeNode:
                try:
                    print("Starting cleanup of temporary nodes...")
                    
                    # Multiple delays and process events
                    time.sleep(0.2)
                    slicer.app.processEvents()
                    
                    # Check if node still exists before removing
                    node_id = labelmapVolumeNode.GetID()
                    if slicer.mrmlScene.GetNodeByID(node_id):
                        print(f"Removing node: {labelmapVolumeNode.GetName()}")
                        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
                        print("Node removed successfully")
                        
                        # Extra processing to ensure cleanup
                        slicer.app.processEvents()
                        time.sleep(0.1)
                        
                        # Verify removal
                        if not slicer.mrmlScene.GetNodeByID(node_id):
                            print("Node cleanup verified")
                        else:
                            print("Warning: Node still exists after removal")
                    else:
                        print("Node was already removed")
                        
                    # Final cleanup
                    slicer.app.processEvents()
                    time.sleep(0.1)
                    
                    print("Cleanup completed successfully")
                    
                except Exception as cleanup_error:
                    print(f"Error cleaning up labelmap node: {str(cleanup_error)}")
                    # Don't show error dialog for cleanup issues
                    
            print("_saveThroughLabelmap function completed")

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