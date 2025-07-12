#!/usr/bin/env python3
"""
Script para probar la funcionalidad de selección de directorio
"""

import sys
import os

# Simular la estructura básica para probar el diálogo de archivos
try:
    import qt
    print("Qt módulo disponible")
    
    # Probar si el diálogo de archivos funciona
    app = qt.QApplication(sys.argv) if not qt.QApplication.instance() else qt.QApplication.instance()
    
    # Probar diálogo de directorio
    directory = qt.QFileDialog.getExistingDirectory(
        None, 
        "Seleccionar Directorio de Prueba", 
        os.path.expanduser("~")
    )
    
    if directory:
        print(f"Directorio seleccionado: {directory}")
    else:
        print("No se seleccionó ningún directorio")
        
except ImportError as e:
    print(f"Error de importación: {e}")
    print("Es probable que este script deba ejecutarse dentro de 3D Slicer")
except Exception as e:
    print(f"Error: {e}")
