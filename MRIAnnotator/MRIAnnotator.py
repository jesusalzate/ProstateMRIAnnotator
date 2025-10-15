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

        # Button to select channel modalities (RGB)
        self.selectChannelModalitiesButton = qt.QPushButton("Select Channel Modalities (RGB)")
        self.selectChannelModalitiesButton.setToolTip("Choose which CSV columns to display in Red, Yellow, and Green channels.")
        self.selectChannelModalitiesButton.clicked.connect(self.onSelectChannelModalities)
        self.layout.addWidget(self.selectChannelModalitiesButton)
        self.selectedChannelModalities = {'Red': 'T2', 'Yellow': 'ADC', 'Green': 'DWI'}

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

        # Button to toggle report visibility
        self.toggleReportButton = qt.QPushButton("Ocultar Reporte")
        self.toggleReportButton.setToolTip("Ocultar/Mostrar el reporte de texto médico")
        self.toggleReportButton.connect('clicked(bool)', self.onToggleReportButton)
        self.layout.addWidget(self.toggleReportButton)

        # Text Report Viewer (for displaying report TXT in 3D view area)
        self.reportViewer = qt.QTextBrowser()
        self.reportViewer.setMinimumHeight(300)
        self.reportViewer.setText("No report loaded")
        
        # Report group
        reportGroup = qt.QGroupBox("Medical Report (TXT)")
        reportLayout = qt.QVBoxLayout()
        reportLayout.addWidget(self.reportViewer)
        reportGroup.setLayout(reportLayout)
        self.layout.addWidget(reportGroup)

        self.linkSliceViews()
        
        # Style buttons (after all buttons are created)
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
        for btn in [self.loadCSVButton, self.browseDirectoryButton, self.nextButton, self.previousButton, self.saveSegmentationImageButton, self.selectChannelModalitiesButton, self.toggleReportButton]:
            btn.setStyleSheet(button_style)
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(120)
        
        # Initialize tracking of loaded nodes for safe removal
        self.loadedVolumeNodes = []
        self.loadedSegmentationNode = None
        self.segmentEditorNode = None
        self.imagePaths = []
        self.currentIndex = -1
        self.segmentedIndices = set()
        self.hasUnsavedChanges = False  # Track if there are unsaved segmentation changes

        self.currentReportPath = None
        self.reportVisible = True  # Track report visibility state (visible by default)

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
            
            # Store original CSV path for later use
            self.original_csv_path = csvPath
            
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
                    
            # Auto-configure channel modalities if CSV has been loaded
            if self.imagePaths:
                self._autoConfigureChannelModalities()
                    
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load CSV: {str(e)}")

    def _autoConfigureChannelModalities(self):
        """
        Auto-configure channel modalities based on available CSV columns.
        Tries to maintain existing selections or use intelligent defaults.
        """
        if not self.imagePaths:
            return
            
        available_columns = list(self.imagePaths[0].keys())
        print(f"Available CSV columns: {available_columns}")
        
        # Filter out ID and tumor columns for channel assignment
        image_columns = [col for col in available_columns 
                        if isinstance(col, str) and 
                        col.upper() not in ['ID'] and 
                        'tumor' not in col.lower()]
        
        print(f"Available image columns for channels: {image_columns}")
        
        # Smart defaults based on common naming patterns
        default_mapping = {
            'Red': self._findColumnByPatterns(['T2', 't2', 'T2W', 't2w'], image_columns),
            'Yellow': self._findColumnByPatterns(['ADC', 'adc'], image_columns),
            'Green': self._findColumnByPatterns(['DWI', 'dwi', 'DWB', 'dwb'], image_columns)
        };
        
        # Update channel modalities, keeping existing selections if they're still valid
        for channel in ['Red', 'Yellow', 'Green']:
            current_selection = self.selectedChannelModalities.get(channel)
            if current_selection and current_selection in image_columns:
                # Keep current selection if still valid
                continue
            elif default_mapping[channel]:
                # Use smart default
                self.selectedChannelModalities[channel] = default_mapping[channel]
            elif image_columns:
                # Use first available column as fallback
                self.selectedChannelModalities[channel] = image_columns[0]
            else:
                # No suitable columns found
                self.selectedChannelModalities[channel] = None
                
        print(f"Configured channel modalities: {self.selectedChannelModalities}")
        slicer.util.infoDisplay(f"Channel modalities configured: Red={self.selectedChannelModalities['Red']}, Yellow={self.selectedChannelModalities['Yellow']}, Green={self.selectedChannelModalities['Green']}")

    def _findColumnByPatterns(self, patterns, columns):
        """
        Find a column that matches any of the given patterns (case-insensitive).
        
        Parameters:
        - patterns: List of patterns to search for
        - columns: List of available column names
        
        Returns:
        - First matching column name or None
        """
        for pattern in patterns:
            for col in columns:
                if pattern.lower() in col.lower():
                    return col
        return None

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

    def onToggleReportButton(self):
        """
        Handle the event when the 'Toggle Report' button is clicked.
        Shows or hides the report viewer and updates the button text.
        """
        try:
            # Toggle the visibility state
            self.reportVisible = not self.reportVisible
            
            if self.reportVisible:
                # Show the report viewer
                self.reportViewer.show()
                self.toggleReportButton.setText("Ocultar Reporte")
                print("Report viewer shown")
            else:
                # Hide the report viewer
                self.reportViewer.hide()
                self.toggleReportButton.setText("Mostrar Reporte")
                print("Report viewer hidden")
                
        except Exception as e:
            error_msg = f"Error toggling report visibility: {str(e)}"
            print(error_msg)
            slicer.util.errorDisplay(error_msg)

    def hasUnsavedSegmentation(self):
        """
        Check if there is an unsaved segmentation in the current editor.
        """
        segmentationNode = self.segmentEditorWidget.segmentationNode()
        if not segmentationNode:
            return False
        
        segmentation = segmentationNode.GetSegmentation()
        if not segmentation:
            return False
            
        # Check if there are any segments
        return segmentation.GetNumberOfSegments() > 0

    def _getSegmentationPathFromUpdatedCSV(self, imageIndex):
        """
        Get the segmentation path from the updated CSV for the given image index.
        Returns the full path to the segmentation file if it exists, None otherwise.
        """
        if imageIndex < 0 or imageIndex >= len(self.imagePaths):
            return None
            
        try:
            # Get the updated CSV path
            directoryPath = self.directoryPathEdit.text
            if not directoryPath:
                return None
                
            original_csv_name = getattr(self, 'original_csv_path', 'dataset.csv')
            if original_csv_name.endswith('.csv'):
                updated_csv_name = os.path.basename(original_csv_name)[:-4] + '_updated.csv'
            else:
                updated_csv_name = os.path.basename(original_csv_name) + '_updated.csv'
                
            updated_csv_path = os.path.join(directoryPath, updated_csv_name)
            
            # Check if updated CSV exists
            if not os.path.exists(updated_csv_path):
                return None
            
            # Get current patient data
            current_patient = self.imagePaths[imageIndex]
            patient_id = current_patient.get('ID', f'patient_{imageIndex:03d}')
            
            # Read the updated CSV and get the segmentation path
            with open(updated_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row.get('ID') == patient_id:
                        # Get the segmentation path (usually in 't2_tumor_reader1' column)
                        segmentation_path = row.get('t2_tumor_reader1', '').strip()
                        if segmentation_path:
                            full_path = os.path.join(directoryPath, segmentation_path)
                            if os.path.exists(full_path):
                                print(f"Found existing segmentation for patient {patient_id}: {full_path}")
                                return full_path
                            else:
                                print(f"Segmentation path in CSV not found on disk: {full_path}")
                                return None
                        else:
                            return None
            
            return None
            
        except Exception as e:
            print(f"Error getting segmentation path from updated CSV: {e}")
            return None

    def _hasImagePathInUpdatedCSV(self, imageIndex):
        """
        Check if the image at the given index has its path recorded in the updated CSV.
        Returns True if the path exists in the updated CSV, False otherwise.
        """
        if imageIndex < 0 or imageIndex >= len(self.imagePaths):
            return False
            
        try:
            # Get the updated CSV path
            directoryPath = self.directoryPathEdit.text
            if not directoryPath:
                return False
                
            original_csv_name = getattr(self, 'original_csv_path', 'dataset.csv')
            if original_csv_name.endswith('.csv'):
                updated_csv_name = os.path.basename(original_csv_name)[:-4] + '_updated.csv'
            else:
                updated_csv_name = os.path.basename(original_csv_name) + '_updated.csv'
                
            updated_csv_path = os.path.join(directoryPath, updated_csv_name)
            
            # Check if updated CSV exists
            if not os.path.exists(updated_csv_path):
                print(f"Updated CSV not found: {updated_csv_path}")
                return False
            
            # Get current patient data
            current_patient = self.imagePaths[imageIndex]
            patient_id = current_patient.get('ID', f'patient_{imageIndex:03d}')
            
            # Read the updated CSV and check if this patient has a segmentation path
            with open(updated_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row.get('ID') == patient_id:
                        # Check if there's a segmentation path (usually in 't2_tumor_reader1' column)
                        segmentation_path = row.get('t2_tumor_reader1', '').strip()
                        if segmentation_path:
                            print(f"Found segmentation path for patient {patient_id}: {segmentation_path}")
                            return True
                        else:
                            print(f"No segmentation path found for patient {patient_id} in updated CSV")
                            return False
            
            print(f"Patient {patient_id} not found in updated CSV")
            return False
            
        except Exception as e:
            print(f"Error checking updated CSV: {e}")
            return False

    def _hasValidImagePaths(self, imageIndex):
        """
        Check if the image at the given index has valid file paths.
        Returns True if at least one valid image file exists, False otherwise.
        """
        if imageIndex < 0 or imageIndex >= len(self.imagePaths):
            return False
            
        imagePaths = self.imagePaths[imageIndex]
        directoryPath = self.directoryPathEdit.text
        
        # Check if any of the channel modalities have valid paths
        for channel in ['Red', 'Yellow', 'Green']:
            modality = self.selectedChannelModalities.get(channel)
            if modality and modality in imagePaths:
                file_path = os.path.join(directoryPath, imagePaths[modality])
                if os.path.exists(file_path):
                    return True
        
        return False

    def showNavigationWarning(self, action_name):
        """
        Show a warning dialog when navigating to a patient not in the updated CSV.
        Returns True if user wants to continue, False otherwise.
        """
        msg = qt.QMessageBox()
        msg.setIcon(qt.QMessageBox.Warning)
        msg.setWindowTitle("Paciente sin ruta guardada")
        
        msg.setText("Este paciente no tiene una ruta de segmentación guardada en el CSV actualizado.")
        msg.setInformativeText(f"¿Desea continuar con '{action_name}' de todos modos?\n\nEste paciente podría necesitar ser procesado.")
        
        msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        msg.setDefaultButton(qt.QMessageBox.Yes)  # Changed to Yes as default since this is more of an info warning
        
        result = msg.exec_()
        return result == qt.QMessageBox.Yes

    def onNextButton(self):
        """
        Handle the event when the 'Next' button is clicked.
        Loads the next set of images from the CSV file.
        """
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        next_index = self.currentIndex + 1
        if next_index >= len(self.imagePaths):
            slicer.util.infoDisplay("No more images.")
            return

        # Show warning only if the next image is NOT in the updated CSV
        if not self._hasImagePathInUpdatedCSV(next_index):
            if not self.showNavigationWarning("Next"):
                return  # User chose not to continue
        
        self.currentIndex = next_index
        self._loadCurrentPatientImages()
        # No update segmentation progress automatically - only when user saves manually

    def onPreviousButton(self):
        """
        Handle the event when the 'Previous' button is clicked.
        Loads the previous set of images from the CSV file.
        """
        if not self.imagePaths:
            slicer.util.errorDisplay("No images loaded from CSV.")
            return

        previous_index = self.currentIndex - 1
        if previous_index < 0:
            slicer.util.infoDisplay("No previous images.")
            return

        # Show warning only if the previous image is NOT in the updated CSV
        if not self._hasImagePathInUpdatedCSV(previous_index):
            if not self.showNavigationWarning("Previous"):
                return  # User chose not to continue
        
        self.currentIndex = previous_index
        self._loadCurrentPatientImages()
        # No update segmentation progress automatically - only when user saves manually

    def _loadCurrentPatientImages(self):
        """
        Load the current patient images using the selected channel modalities.
        """
        print(f"_loadCurrentPatientImages called with currentIndex: {self.currentIndex}")
        
        if self.currentIndex < 0 or self.currentIndex >= len(self.imagePaths):
            print("Invalid currentIndex, cannot load images")
            return
            
        imagePaths = self.imagePaths[self.currentIndex]
        directoryPath = self.directoryPathEdit.text
        
        print(f"Directory path: {directoryPath}")
        print(f"Image paths from CSV: {imagePaths}")
        
        # Get paths based on selected channel modalities
        channel_paths = {}
        for channel in ['Red', 'Yellow', 'Green']:
            modality = self.selectedChannelModalities.get(channel)
            if modality and modality in imagePaths:
                channel_paths[channel] = os.path.join(directoryPath, imagePaths[modality])
                print(f"{channel} channel: {modality} -> {channel_paths[channel]}")
            else:
                channel_paths[channel] = None
                print(f"{channel} channel: No modality assigned or not found in CSV")
        
        # First check if there's an existing segmentation in the updated CSV
        existing_segmentation_path = self._getSegmentationPathFromUpdatedCSV(self.currentIndex)
        
        if existing_segmentation_path:
            # Use the existing segmentation from the updated CSV
            lesionPath = existing_segmentation_path
            print(f"Using existing segmentation from updated CSV: {lesionPath}")
        else:
            # Get lesion path using selected segmentation modality from original CSV
            lesion_col = self.selectedSegmentationModality if hasattr(self, 'selectedSegmentationModality') and self.selectedSegmentationModality else 'Lesion'
            lesionPath = os.path.join(directoryPath, imagePaths.get(lesion_col, ''))
            print(f"No existing segmentation found, using original CSV path: {lesionPath}")
        
        # Debug prints
        print(f"Selected channel modalities: {self.selectedChannelModalities}")
        print(f"Channel paths: {channel_paths}")
        print(f"Selected segmentation modality: {lesion_col if not existing_segmentation_path else 'from updated CSV'}")
        print(f"Final lesion path: {lesionPath}")
        print(f"Available columns: {list(imagePaths.keys())}")

        print("Calling _loadPatientImagesWithCustomChannels...")
        
        # Remove previous images and clear all segmentations before loading new patient
        print("Removing previous images and clearing segmentations before loading new patient")
        self.removePreviousImages()
        
        self._loadPatientImagesWithCustomChannels(channel_paths, lesionPath)
        print("_loadCurrentPatientImages completed")

        # Show TXT report if present
        self.showReportTXT(imagePaths)

    def showReportTXT(self, imagePaths):
        """
        Display the TXT pointed to by the 'report' column in the sidebar report viewer.
        """
        print("[TXT] showReportTXT called")
        report_path = imagePaths.get('report', None)
        print(f"[TXT] report_path from CSV: {report_path}")

        if report_path:
            directoryPath = self.directoryPathEdit.text
            print(f"[TXT] directoryPath: {directoryPath}")
            abs_report_path = os.path.join(directoryPath, report_path) if not os.path.isabs(report_path) else report_path
            print(f"[TXT] abs_report_path: {abs_report_path}")
            
            if os.path.exists(abs_report_path) and abs_report_path.lower().endswith('.txt'):
                self.currentReportPath = abs_report_path
                try:
                    # Read and display the TXT file content in sidebar
                    print("[TXT] Reading TXT file content")
                    with open(abs_report_path, 'r', encoding='utf-8') as f:
                        txt_content = f.read()
                    self.reportViewer.setText(txt_content)
                    print("[TXT] Report content loaded in sidebar viewer")
                    
                except Exception as e:
                    print(f"[TXT] Error reading TXT file: {e}")
                    self.reportViewer.setText(f"Error reading report file: {str(e)}")
            else:
                print("[TXT] No valid TXT found")
                self.currentReportPath = None
                self.reportViewer.setText("No valid TXT report found for this patient.")
        else:
            print("[TXT] No report for this patient")
            self.currentReportPath = None
            self.reportViewer.setText("No report available for this patient.")
        
        # Respect the current visibility state
        if self.reportVisible:
            self.reportViewer.show()
        else:
            self.reportViewer.hide()

    def _loadPatientImages(self, t2Path, adcPath, dwiPath, lesionPath):
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
        # Clear any previous segmentation from the editor widget first
        print("Clearing previous segmentation from editor widget")
        self.segmentEditorWidget.setSegmentationNode(None)
        self.segmentEditorWidget.setSourceVolumeNode(None)
        
        # Process events to ensure clearing is complete
        slicer.app.processEvents()
        
        segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        # Track segment editor node for cleanup
        self.segmentEditorNode = segmentEditorNode
        self.segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
        
        if segmentationNode is None:
            print("Creating new empty segmentation node")
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            segmentationNode.SetName("Segmentation")
        else:
            print(f"Using existing segmentation node: {segmentationNode.GetName()}")
            
        self.segmentEditorWidget.setSegmentationNode(segmentationNode)
        self.segmentEditorWidget.setSourceVolumeNode(masterVolumeNode)
        
        # Connect to segmentation changes to track unsaved changes
        if segmentationNode:
            segmentationNode.GetSegmentation().AddObserver(
                segmentationNode.GetSegmentation().SegmentAdded, 
                self.onSegmentationChanged
            )
            segmentationNode.GetSegmentation().AddObserver(
                segmentationNode.GetSegmentation().SegmentRemoved, 
                self.onSegmentationChanged
            )
            segmentationNode.GetSegmentation().AddObserver(
                segmentationNode.GetSegmentation().SegmentModified, 
                self.onSegmentationChanged
            )
        
        # Reset unsaved changes flag when loading new patient
        self.hasUnsavedChanges = False
        
        # Ensure the segmentation is properly displayed
        slicer.app.processEvents()

    def onSegmentationChanged(self, caller, event):
        """
        Called when the segmentation is modified. Marks that there are unsaved changes.
        """
        self.hasUnsavedChanges = True
        print("Segmentation changed - marking as having unsaved changes")

    def clearAllSegmentations(self):
        """
        Clear all segmentations from slice views and segment editor.
        """
        print("Clearing all segmentations from views")
        
        # Clear segment editor widget
        self.segmentEditorWidget.setSegmentationNode(None)
        self.segmentEditorWidget.setSourceVolumeNode(None)
        
        # Clear segmentations from all slice views
        lm = slicer.app.layoutManager()
        for sliceViewName in ['Red', 'Yellow', 'Green']:
            sliceWidget = lm.sliceWidget(sliceViewName)
            sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
            sliceCompositeNode.SetLabelVolumeID(None)
            # Also clear any segmentation overlays
            sliceView = sliceWidget.sliceView()
            if sliceView:
                sliceView.forceRender()
        
        # Hide all segmentation nodes in the scene
        segmentationNodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        for segNode in segmentationNodes:
            displayNode = segNode.GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(False)
                
        slicer.app.processEvents()

    def removePreviousImages(self):
        """
        Safely remove previously loaded images, segmentations, and editor nodes.
        """
        print("Removing previous images and segmentations")
        
        # Clear all segmentations first
        self.clearAllSegmentations()
        
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
            
        slicer.app.processEvents()

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
        Si no hay segmentación, guarda un archivo empty.nii.gz.
        Actualiza el CSV con la ruta del archivo guardado.
        """
        if not hasattr(self, 'imagePaths') or self.currentIndex < 0:
            slicer.util.errorDisplay("No hay paciente actual cargado.")
            return
            
        # Obtener información del paciente actual
        current_row = self.imagePaths[self.currentIndex]
        patient_id = current_row.get('ID', f'patient_{self.currentIndex:03d}')
        
        # Obtener el nodo de segmentación actual
        segmentationNode = self.segmentEditorWidget.segmentationNode()
        has_segments = False
        
        if segmentationNode:
            segmentation = segmentationNode.GetSegmentation()
            if segmentation and segmentation.GetNumberOfSegments() > 0:
                has_segments = True

        # Configurar nombre por defecto y directorio
        directoryPath = self.directoryPathEdit.text
        if not directoryPath:
            slicer.util.errorDisplay("No se ha configurado el directorio raíz.")
            return
            
        # Crear carpeta "edited" dentro del directorio raíz
        edited_folder = os.path.join(directoryPath, "edited")
        if not os.path.exists(edited_folder):
            os.makedirs(edited_folder)
            print(f"Created 'edited' folder: {edited_folder}")
            
        # Crear estructura de carpetas: directorio_raiz/edited/patient_id/
        patient_folder = os.path.join(edited_folder, patient_id)
        if not os.path.exists(patient_folder):
            os.makedirs(patient_folder)
            print(f"Created patient folder: {patient_folder}")
            
        # Nombre por defecto del archivo
        default_filename = "t2_tumor_reader1.nii.gz"
        default_full_path = os.path.join(patient_folder, default_filename)
        
        # Pedir al usuario que seleccione la ubicación y nombre del archivo
        if has_segments:
            dialog_title = "Guardar segmentación como NIfTI"
        else:
            dialog_title = "Guardar archivo vacío como NIfTI"
            
        output_path = qt.QFileDialog.getSaveFileName(
            self.parent, 
            dialog_title,
            default_full_path,
            "NIfTI Files (*.nii.gz);;NIfTI Files (*.nii)")

        if not output_path:
            return  # El usuario canceló

        # Asegurarse de que la extensión sea .nii.gz
        if not output_path.endswith('.nii.gz'):
            output_path += '.nii.gz'

        try:
            if has_segments:
                # Guardar segmentación normal
                labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
                slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                    segmentationNode, labelmapVolumeNode)
                slicer.util.saveNode(labelmapVolumeNode, output_path)
                slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
                slicer.util.infoDisplay(f"Segmentación guardada exitosamente en: {output_path}")
            else:
                # Crear archivo empty.nii.gz
                self._createEmptyNiftiFile(output_path)
                slicer.util.infoDisplay(f"Archivo vacío guardado exitosamente en: {output_path}")
                
            # Calcular ruta relativa desde el directorio raíz
            relative_path = os.path.relpath(output_path, directoryPath)
            relative_path = relative_path.replace('\\', '/')  # Usar barras forward para compatibilidad
            
            # Actualizar el CSV con la nueva ruta
            self._updateCSVWithSegmentationPath(relative_path)
                
            # Mark current patient as segmented and update progress
            if 0 <= self.currentIndex < len(self.imagePaths):
                self.segmentedIndices.add(self.currentIndex)
                self.updateSegmentationProgress()
                print(f"Marked patient {self.currentIndex} as segmented")
            
            # Mark that changes have been saved
            self.hasUnsavedChanges = False
            print("Segmentation saved - clearing unsaved changes flag")
                
        except Exception as e:
            slicer.util.errorDisplay(f"Error al guardar: {str(e)}")
            if 'labelmapVolumeNode' in locals() and labelmapVolumeNode:
                slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def onSelectChannelModalities(self):
        """
        Show a dialog to select which CSV columns to display in each color channel (Red, Yellow, Green).
        """
        if not hasattr(self, 'imagePaths') or not self.imagePaths:
            slicer.util.errorDisplay("Load a CSV first.")
            return
            
        available_columns = list(self.imagePaths[0].keys())
        print(f"All available columns: {available_columns}")
        
        # Filter out ID and tumor columns for channel assignment
        image_columns = [col for col in available_columns 
                        if isinstance(col, str) and 
                        col.upper() not in ['ID'] and 
                        'tumor' not in col.lower()]
        
        if not image_columns:
            slicer.util.errorDisplay("No suitable image columns found in CSV.")
            return
            
        print(f"Available image columns: {image_columns}")
        
        # Create a custom dialog for channel selection
        dialog = qt.QDialog(self.parent)
        dialog.setWindowTitle("Select Channel Modalities")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = qt.QVBoxLayout(dialog)
        
        # Instructions
        instructions = qt.QLabel("Select which CSV column to display in each color channel:")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(instructions)
        
        # Create combo boxes for each channel
        channel_combos = {}
        channel_colors = {'Red': '#ff4444', 'Yellow': '#ffdd44', 'Green': '#44ff44'}
        
        for channel in ['Red', 'Yellow', 'Green']:
            # Channel label with color indicator
            channel_layout = qt.QHBoxLayout()
            
            color_indicator = qt.QLabel("■")
            color_indicator.setStyleSheet(f"color: {channel_colors[channel]}; font-size: 20px; font-weight: bold;")
            color_indicator.setFixedWidth(20)
            
            channel_label = qt.QLabel(f"{channel} Channel:")
            channel_label.setStyleSheet("font-weight: bold;")
            channel_label.setFixedWidth(100)
            
            combo = qt.QComboBox()
            combo.addItems(['None'] + image_columns)
            
            # Set current selection
            current_modality = self.selectedChannelModalities.get(channel)
            if current_modality and current_modality in image_columns:
                combo.setCurrentText(current_modality)
            else:
                combo.setCurrentText('None')
                
            channel_combos[channel] = combo
            
            channel_layout.addWidget(color_indicator)
            channel_layout.addWidget(channel_label)
            channel_layout.addWidget(combo)
            channel_layout.addStretch()
            
            layout.addLayout(channel_layout)
        
        # Add some spacing
        layout.addSpacing(20)
        
        # Buttons
        button_layout = qt.QHBoxLayout()
        
        ok_button = qt.QPushButton("OK")
        cancel_button = qt.QPushButton("Cancel")
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # Connect buttons
        ok_button.clicked.connect(lambda: dialog.accept())
        cancel_button.clicked.connect(lambda: dialog.reject())
        
        # Show dialog and process result
        if dialog.exec_() == qt.QDialog.Accepted:
            print("Dialog accepted - processing channel modality changes...")
            
            # Update selected modalities
            old_modalities = dict(self.selectedChannelModalities)  # Save old state for comparison
            
            for channel in ['Red', 'Yellow', 'Green']:
                selected_text = channel_combos[channel].currentText
                if selected_text == 'None':
                    self.selectedChannelModalities[channel] = None
                else:
                    self.selectedChannelModalities[channel] = selected_text
                    
            print(f"Old channel modalities: {old_modalities}")
            print(f"New channel modalities: {self.selectedChannelModalities}")
            
            # Check if anything actually changed
            changes_made = old_modalities != self.selectedChannelModalities
            print(f"Changes made: {changes_made}")
            
            if changes_made:
                slicer.util.infoDisplay(f"Channel modalities updated: Red={self.selectedChannelModalities['Red']}, Yellow={self.selectedChannelModalities['Yellow']}, Green={self.selectedChannelModalities['Green']}")
                
                # Force refresh the interface with new channel assignments
                if self.currentIndex >= 0:
                    print("Refreshing interface with new channel configuration...")
                    self._refreshInterfaceWithNewChannels()
                else:
                    print("No current image loaded - configuration will be applied on next image load")
                    slicer.util.infoDisplay("Configuration saved. Will be applied when images are loaded.")
            else:
                print("No changes made to channel modalities")
                slicer.util.infoDisplay("No changes made to channel configuration.")
        else:
            print("Channel modality selection cancelled")

    def _refreshInterfaceWithNewChannels(self):
        """
        Refresh the entire interface with the new channel modality configuration.
        This ensures all views are properly updated and synchronized.
        """
        if self.currentIndex < 0 or self.currentIndex >= len(self.imagePaths):
            print("No valid current index for refresh")
            return
            
        try:
            import time
            import traceback
            
            print(f"Starting interface refresh for index {self.currentIndex}")
            print(f"Current channel modalities: {self.selectedChannelModalities}")
            
            # Save current state before refresh
            current_seg_node = self.segmentEditorWidget.segmentationNode()
            print(f"Current segmentation node: {current_seg_node}")
            
            # Clear slice views first to prevent conflicts
            print("Clearing slice views...")
            self._clearAllSliceViews()
            
            # Small delay to ensure clearing is complete
            slicer.app.processEvents()
            time.sleep(0.1)
            
            # Remove previous nodes to avoid conflicts
            print("Removing previous images...")
            self.removePreviousImages()
            
            # Small delay after removal
            slicer.app.processEvents()
            time.sleep(0.1)
            
            # Load images with new channel configuration
            print("Loading images with new configuration...")
            self._loadCurrentPatientImages()
            
            # Restore segmentation if it existed
            if current_seg_node and current_seg_node.GetSegmentation().GetNumberOfSegments() > 0:
                print("Preserving existing segmentation after refresh")
                # The segmentation should be preserved through the segment editor widget
            
            # Ensure slice views are properly linked and fitted
            print("Linking slice views and fitting...")
            self.linkSliceViews()
            slicer.app.applicationLogic().FitSliceToAll()
            
            print("Interface refresh completed successfully")
            slicer.util.infoDisplay("Interface refreshed with new channel configuration!")
            
        except Exception as e:
            print(f"Error during interface refresh: {str(e)}")
            import traceback
            traceback.print_exc()
            slicer.util.errorDisplay(f"Error refreshing interface: {str(e)}")

    def _clearAllSliceViews(self):
        """
        Clear all slice views to prepare for new image loading.
        """
        lm = slicer.app.layoutManager()
        
        for channel in ['Red', 'Yellow', 'Green']:
            try:
                sliceWidget = lm.sliceWidget(channel)
                sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
                sliceCompositeNode.SetBackgroundVolumeID(None)
                sliceCompositeNode.SetForegroundVolumeID(None)
                sliceCompositeNode.SetLabelVolumeID(None)
                print(f"Cleared {channel} slice view")
            except Exception as e:
                print(f"Warning: Could not clear {channel} slice view: {str(e)}")
                
        # Process events to ensure clearing is complete
        slicer.app.processEvents()

    def _reloadCurrentImagesWithNewChannels(self):
        """
        Reload the current images using the newly selected channel modalities.
        This method is deprecated in favor of _refreshInterfaceWithNewChannels.
        """
        print("Redirecting to new refresh method...")
        self._refreshInterfaceWithNewChannels()

    def _loadPatientImagesWithCustomChannels(self, channel_paths, lesionPath):
        """
        Load patient images with custom channel assignments.
        
        Parameters:
        - channel_paths: Dictionary with 'Red', 'Yellow', 'Green' keys and file paths as values
        - lesionPath: Path to the lesion segmentation (optional)
        """
        print("_loadPatientImagesWithCustomChannels called")
        print(f"Channel paths: {channel_paths}")
        print(f"Lesion path: {lesionPath}")
        
        try:
            # Load volumes for each channel
            loaded_nodes = {}
            reference_node = None
            
            for channel in ['Red', 'Yellow', 'Green']:
                path = channel_paths.get(channel)
                print(f"Processing {channel} channel with path: {path}")
                
                if path and os.path.exists(path):
                    print(f"Loading volume from {path}")
                    node = self.loadVolume(path)
                    loaded_nodes[channel] = node
                    if reference_node is None:  # Use first loaded node as reference
                        reference_node = node
                        print(f"Set {channel} as reference node")
                    print(f"Successfully loaded {channel} channel: {path}")
                else:
                    loaded_nodes[channel] = None
                    if path:
                        print(f"Warning: {channel} channel file not found: {path}")
                    else:
                        print(f"No modality assigned to {channel} channel")
            
            print(f"Loaded nodes: {[ch for ch, node in loaded_nodes.items() if node is not None]}")
            
            if reference_node is None:
                print("No valid image files found for any channel")
                slicer.util.errorDisplay("No valid image files found for any channel.")
                return
                
            # Load lesion segmentation if available
            lesionNode = None
            if lesionPath and os.path.isfile(lesionPath):
                print(f"Loading lesion segmentation from: {lesionPath}")
                lesionNode = self.loadSegmentation(lesionPath, reference_node)
                print(f"Successfully loaded lesion segmentation: {lesionPath}")
            else:
                print("No lesion segmentation found for this session.")
                
            # Track loaded nodes for removal
            self.loadedVolumeNodes = [node for node in loaded_nodes.values() if node is not None]
            self.loadedSegmentationNode = lesionNode
            print(f"Tracking {len(self.loadedVolumeNodes)} volume nodes and segmentation node: {lesionNode is not None}")
            
            # Resample all images to reference space
            print("Resampling images to reference space...")
            self._resampleImagesToReference(loaded_nodes, reference_node)
            
            # Setup segment editor
            print("Setting up segment editor...")
            self.setupSegmentEditor(reference_node, lesionNode)
            
            # Assign images to slice views
            print("Assigning images to slice views...")
            self._assignCustomImagesToSliceViews(loaded_nodes)
            
            print("_loadPatientImagesWithCustomChannels completed successfully")
            
        except Exception as e:
            print(f"Error in _loadPatientImagesWithCustomChannels: {str(e)}")
            import traceback
            traceback.print_exc()
            slicer.util.errorDisplay(f"Failed to load images: {str(e)}")

    def _resampleImagesToReference(self, loaded_nodes, reference_node):
        """
        Resample all loaded images to the reference node space.
        
        Parameters:
        - loaded_nodes: Dictionary of channel->node mappings
        - reference_node: Reference volume node
        """
        reference_image = sitkUtils.PullVolumeFromSlicer(reference_node)
        
        for channel, node in loaded_nodes.items():
            if node and node != reference_node:
                try:
                    node_image = sitkUtils.PullVolumeFromSlicer(node)
                    resampled_image = self.resample_to_reference_scan(
                        image=node_image,
                        reference_scan_original=reference_image
                    )
                    sitkUtils.PushVolumeToSlicer(resampled_image, node)
                    print(f"Resampled {channel} channel to reference space")
                except Exception as e:
                    print(f"Warning: Could not resample {channel} channel: {str(e)}")

    def _assignCustomImagesToSliceViews(self, loaded_nodes):
        """
        Assign the custom loaded images to the slice views.
        
        Parameters:
        - loaded_nodes: Dictionary with 'Red', 'Yellow', 'Green' keys and volume nodes as values
        """
        lm = slicer.app.layoutManager()
        
        for channel in ['Red', 'Yellow', 'Green']:
            node = loaded_nodes.get(channel)
            if node:
                sliceWidget = lm.sliceWidget(channel)
                sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
                sliceCompositeNode.SetBackgroundVolumeID(node.GetID())
                sliceWidget.mrmlSliceNode().SetOrientationToAxial()
                sliceWidget.sliceController().setSliceLink(True)
                sliceWidget.sliceLogic().FitSliceToAll()
                print(f"Assigned {channel} channel to slice view")
            else:
                # Clear the slice view if no image assigned
                sliceWidget = lm.sliceWidget(channel)
                sliceCompositeNode = sliceWidget.mrmlSliceCompositeNode()
                sliceCompositeNode.SetBackgroundVolumeID(None)
                print(f"Cleared {channel} channel slice view")

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
    
    def _updateCSVWithSegmentationPath(self, segmentation_relative_path):
        """
        Update the CSV file with the new segmentation path for the current patient.
        Creates a new CSV file with the updated information.
        """
        if not hasattr(self, 'imagePaths') or not self.imagePaths:
            print("No CSV data to update")
            return
            
        try:
            # Update the current row with the new segmentation path
            current_row = self.imagePaths[self.currentIndex].copy()
            current_row['t2_tumor_reader1'] = segmentation_relative_path
            
            # Update the in-memory data
            self.imagePaths[self.currentIndex] = current_row
            
            # Create output CSV filename
            directoryPath = self.directoryPathEdit.text
            if not directoryPath:
                print("No directory path set")
                return
                
            # Generate output CSV name (add _updated suffix)
            original_csv_name = getattr(self, 'original_csv_path', 'dataset.csv')
            if original_csv_name.endswith('.csv'):
                output_csv_name = original_csv_name[:-4] + '_updated.csv'
            else:
                output_csv_name = original_csv_name + '_updated.csv'
                
            output_csv_path = os.path.join(directoryPath, os.path.basename(output_csv_name))
            
            # Write updated CSV
            if self.imagePaths:
                fieldnames = list(self.imagePaths[0].keys())
                with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(self.imagePaths)
                    
                print(f"CSV updated successfully: {output_csv_path}")
                print(f"Updated t2_tumor_reader1 for patient {self.currentIndex}: {segmentation_relative_path}")
                
        except Exception as e:
            print(f"Error updating CSV: {str(e)}")
            slicer.util.errorDisplay(f"Error updating CSV: {str(e)}")

    def _createEmptyNiftiFile(self, output_path):
        """
        Create an empty NIfTI file with the same dimensions as the current reference volume.
        """
        # Get the current source volume as reference
        sourceVolumeNode = self.segmentEditorWidget.sourceVolumeNode()
        if not sourceVolumeNode:
            # If no source volume, create a minimal empty file
            with open(output_path, 'wb') as f:
                pass
            print(f"Created minimal empty file: {output_path}")
            return
            
        try:
            # Get the source volume image data
            sourceImage = sitkUtils.PullVolumeFromSlicer(sourceVolumeNode)
            
            # Create an empty image with the same dimensions and spacing
            emptyImage = sitk.Image(sourceImage.GetSize(), sitk.sitkUInt8)
            emptyImage.CopyInformation(sourceImage)
            
            # Fill with zeros (already is, but explicit)
            emptyImage = emptyImage * 0
            
            # Save as NIfTI
            sitk.WriteImage(emptyImage, output_path)
            print(f"Created empty NIfTI file with reference dimensions: {output_path}")
            
        except Exception as e:
            print(f"Error creating empty NIfTI with reference dimensions: {e}")
            # Fallback: create minimal empty file
            with open(output_path, 'wb') as f:
                pass
            print(f"Created minimal empty file as fallback: {output_path}")

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