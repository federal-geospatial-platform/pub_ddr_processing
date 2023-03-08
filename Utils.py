# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
# pylint: disable=too-many-lines
# pylint: disable=useless-return
# pylint: disable=too-few-public-methods
# pylint: disable=relative-beyond-top-level

# /***************************************************************************
# ddr_algorithm.py
# ----------
# Date                 : January 2021
# copyright            : (C) 2023 by Natural Resources Canada
# email                : daniel.pilon@canada.ca
#
#  ***************************************************************************/
#
# /***************************************************************************
#  *                                                                         *
#  *   This program is free software; you can redistribute it and/or modify  *
#  *   it under the terms of the GNU General Public License as published by  *
#  *   the Free Software Foundation; either version 2 of the License, or     *
#  *   (at your option) any later version.                                   *
#  *                                                                         *
#  ***************************************************************************/

"""
QGIS Plugin for DDR manipulation
"""

import os
import http.client
import inspect
import json
import requests
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (Qgis, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterDistance,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
                       QgsFeatureSink, QgsFeatureRequest, QgsLineString, QgsWkbTypes, QgsGeometry,
                       QgsProcessingException, QgsProcessingParameterMultipleLayers, QgsMapLayer,
                       QgsVectorLayerExporter, QgsVectorFileWriter, QgsProject, QgsProcessingParameterEnum,
                       QgsProcessingParameterString, QgsProcessingParameterFolderDestination,
                       QgsMapLayerStyleManager, QgsReadWriteContext, QgsDataSourceUri,  QgsDataProvider,
                       QgsProviderRegistry, QgsProcessingParameterAuthConfig,  QgsApplication,  QgsAuthMethodConfig,
                       QgsProcessingParameterFile, QgsProcessingParameterDefinition)

@dataclass
class ControlFile:
    """Declare the fields in the control control file"""

    download_info_id: str = None
    email: str = None
    metadata_uuid: str = None
    qgis_server_id: str = None
    download_package_name: str = ''
    core_subject_term: str = ''
    in_project_filename: str = None
    language: str = None
    gpkg_file_name: str = None           # Name of Geopackage containing the vector layers
    control_file_dir: str = None         # Name of temporary directory
    control_file_name: str = None        # Name of the control file
    zip_file_name: str = None            # Name of the zip file
    keep_files: str = None               # Name of the flag to keep the temporary files and directory
    json_document: str = None            # Name of the JSON document
    dst_qgs_project_name: str = None     # Name of the output QGIS project file
    qgis_project_file_en: str = None     # Name of the input English QGIS project file
    qgis_project_file_fr: str = None     # Name of the input French QGIS project file
    out_qgs_project_file_en: str = None  # Name out the output English project file
    out_qgs_project_file_fr: str = None  # Name out the output English project file
    validation_type: str = None          # Name of the type of validation


class UserMessageException(Exception):
    """Exception raised when a message (likely an error message) needs to be sent to the User."""
    pass