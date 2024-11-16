cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(ProstateMRIAnnotator)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/ProstateMRIAnnotator")
set(EXTENSION_CATEGORY "Annotation Tool")
set(EXTENSION_CONTRIBUTORS "Jesus Alejandro Alzate-Grisales (UMIB-IA)")
set(EXTENSION_DESCRIPTION "This is an extension for multimodality MRI segmentation for Prostate Cancer (T2w, DWI and ADC imaging)")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/ProstateMRIAnnotator.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/ProstateMRIAnnotator/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
