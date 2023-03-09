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


class LoginToken(object):
    """This class manages the login token needed to call the different DDR API end points"""

    # Class variable used to verify that the login class has been set
    __initialization_flag = False

    # Class variable used to store the unique value of the login
    __token = None

    @staticmethod
    def set_token(token):
        """This method sets the token """

        LoginToken.__token = token
        LoginToken.__initialization_flag = True

    @staticmethod
    def get_token(feedback):
        """This method allows to get the token. If the token is None than an error is rose because the login  was
           not done"""

        if not LoginToken.__initialization_flag:
            # The token has hot been initialised (no login)
            Utils.push_info(feedback, f"ERROR: Login first...")
            raise UserMessageException("The user must login first before doing any access to the DDR")

        return LoginToken.__token


class DdrInfo(object):
    """This class holds and manages different information extracted from the DDR using the API"""

    # Class variable used to verify that the DdrInfo class has been set
    __initialization_flag = False

    # Class variables used to store the content of the DdrInfo class
    __qgis_layer_name_en = None
    __qgis_layer_name_fr = None
    __short_name_en = None
    __short_name_fr = None
    __json_theme = []
    __json_department = []
    __json_email = []
    __json_downloads = None
    __json_servers = None

    @staticmethod
    def init_project_file():
        """Initiasize the variable of the project file"""

        DdrInfo.__qgis_layer_name_en = []
        DdrInfo.__qgis_layer_name_fr = []
        DdrInfo.__short_name_en = []
        DdrInfo.__short_name_fr = []

    @staticmethod
    def add_layer(src_layer, language):
        """Validate that the short name is present and not duplicate between the layers"""

        short_name = src_layer.shortName()

        # validate that the short name is present
        if short_name is None or short_name == "":
            raise UserMessageException(f"The short name for layer {src_layer.name()} is missing")

        # Validate that the short name is not duplicate
        if language == "EN":
            qgis_layer_name = DdrInfo.__qgis_layer_name_en
        else:
            qgis_layer_name = DdrInfo.__qgis_layer_name_fr

        if short_name not in qgis_layer_name:
            qgis_layer_name.append(short_name)
        else:
            raise UserMessageException(f"Duplicate short name {short_name} for layer {src_layer.name()}")

    @staticmethod
    def get_layer_short_name(src_layer):
        """Get the short name from the layer"""

        return src_layer.shortName()

    @staticmethod
    def get_nbr_layers():

        a = len(DdrInfo.__qgis_layer_name_en)
        b = len(DdrInfo.__qgis_layer_name_fr)
        return max(a, b)

    @staticmethod
    def add_email(json_email):
        """Add the email associated to the login"""

        DdrInfo.__json_email = json_email

    @staticmethod
    def get_email():
        """Get the login associated to the login"""

        return DdrInfo.__json_email

    @staticmethod
    def add_departments(json_department):
        """Add the the departments from the JSON response structure
           Verify the validity of the JSON structure"""

        DdrInfo.__json_department = json_department
        # Verify the structure/content of the JSON document
        try:
            for item in DdrInfo.__json_department:
                acronym = item['qgis_data_store_root_subpath']
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON theme response from the DDR request")

    @staticmethod
    def get_department_lst():
        """Extract the departments in the form of a list"""

        department_lst = []
        for item in DdrInfo.__json_department:
            department = item['qgis_data_store_root_subpath']
            department_lst.append(department)

        return department_lst

    @staticmethod
    def add_themes(json_theme):
        """Add the the themes from the JSON response structure
           Verify the validity of the JSON structure"""

        DdrInfo.__json_theme = json_theme
        # Verify the structure/content of the JSON document
        try:
            for item in DdrInfo.__json_theme:
                theme_uuid = item['theme_uuid']  # Just check that the key 'theme_uuid" exist
                title = item['title']
                # Replace the coma "," by a semi column ";" as QGIS processing enum does not like coma
                title['en'] = title['en'].replace(',', ';')
                title['fr'] = title['fr'].replace(',', ';')
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON theme response from the DDR request")

    @staticmethod
    def get_theme_lst(language):
        """Extract the themes in the form of a list"""

        if language not in ["fr", "en"]:
            raise UserMessageException("Internal error: Invalid language")
        theme_lst = []
        for item in DdrInfo.__json_theme:
            title = item['title']
            theme_lst.append(title[language])

        return theme_lst

    @staticmethod
    def get_theme_uuid(title):
        """Get the theme UUID for a theme title
           Raise an exception if the theme cannot be find in the list (should not happen...)"""

        if title is None or title == "":

            item_uuid = ""
        else:
            item_uuid = None
            for item in DdrInfo.__json_theme:
                item_uuid = item['theme_uuid']
                item_title = item['title']
                item_title_en = item_title['en']
                item_title_fr = item_title['fr']
                if title in (item_title_en, item_title_fr):
                    break

            if item_uuid is None:
                # Nothing was found internal error
                raise UserMessageException(f"Internal error: The 'title' is not found...")

        return item_uuid

    @staticmethod
    def add_downloads(json_downloads):
        """Add the the downloads from the JSON response structure
           Verify the validity of the JSON structure"""

        DdrInfo.__json_downloads = json_downloads
        # Verify the structure/content of the JSON document
        try:
            for item in DdrInfo.__json_downloads:
                id_value = item['id']
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON Downloads response from the DDR request")

    @staticmethod
    def get_downloads_lst():
        """Extract the departments in the form of a list"""

        downloads_lst = []
        if DdrInfo.__json_downloads is not None:
            for item in DdrInfo.__json_downloads:
                id_value = item['id']
                downloads_lst.append(id_value)
        else:
            # Manage the case where the Login is not done and the JSON structure not filed
            downloads_lst = ["<empty>"]

        return downloads_lst

    @staticmethod
    def add_servers(json_servers):
        """Add the the servers from the JSON response structure
           Verify the validity of the JSON structure"""

        DdrInfo.__json_servers = json_servers
        # Verify the structure/content of the JSON document
        try:
            for item in DdrInfo.__json_servers:
                id_value = item['id']
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON Servers response from the DDR request")

    @staticmethod
    def get_servers_lst():
        """Extract the departments in the form of a list"""

        servers_lst = []
        if DdrInfo.__json_servers is not None:
            for item in DdrInfo.__json_servers:
                id_value = item['id']
                servers_lst.append(id_value)
        else:
            # Manage the case where the Login is not done and the JSON structure not filed
            servers_lst = ["<empty>"]

        return servers_lst
