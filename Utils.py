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
#import inspect
import json
import requests
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
#from qgis.PyQt.QtCore import QCoreApplication
#from qgis.PyQt.QtGui import QIcon
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
        try:
            email = DdrInfo.__json_email['email']

        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON theme response from the DDR request")

    @staticmethod
    def get_email():
        """Get the login associated to the login"""

        if DdrInfo.__json_email == []:
            email = " "
        else:
            email = DdrInfo.__json_email['email']

        return email

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


class Utils:
    """Contains a list of static methods"""

#    @staticmethod
#    def process_algorithm(self, process_type, parameters, context, feedback):
#
#        # Init the project files by resetting the layers structures
#        DdrInfo.init_project_file()
#
#        # Create the control file data structure
#        ctl_file = ControlFile()
#
#        # Extract the parameters
#        self.read_parameters(ctl_file, parameters, context, feedback)
#
#        # Copy the QGIS project file (.qgs)
#        Utils.copy_qgis_project_file(ctl_file, feedback)
#
#        # Copy the selected layers in the GPKG file
#        Utils.copy_layer_gpkg(ctl_file, feedback)
#
#        # Set the layer data source
#        Utils.set_layer_data_source(ctl_file, feedback)
#
#        # Creation of the JSON control file
#        Utils.create_json_control_file(ctl_file, feedback)
#
#        # Creation of the ZIP file
#        Utils.create_zip_file(ctl_file, feedback)
#
#        # Validate the project file
#        if process_type == "VALIDATE":
#            DdrValidate.validate_project_file(ctl_file, parameters, context, feedback)
#        elif process_type == "PUBLISH":
#            # Publish the project file
#            DdrPublish.publish_project_file(ctl_file, parameters, context, feedback)
#        elif process_type == "UNPUBLISH":
#            # Unpublish the project file
#            DdrUnpublish.unpublish_project_file(ctl_file, parameters, context, feedback)
#        elif process_type == "UPDATE":
#            # Update the project file
#            DdrUpdate.update_project_file(ctl_file, parameters, context, feedback)
#        else:
#            raise UserMessageException(f"Internal error. Unknown Process Type: {process_type}")
#
#        # Restoring original .qgs project file
#        Utils.restore_original_project_file(ctl_file, feedback)
#
#        # Deleting the temporary directory and files
#        # import web_pdb; web_pdb.set_trace()
#        Utils.delete_dir_file(ctl_file, feedback)
#
#        return

    @staticmethod
    def get_date_time():
        """Extract the current date and time """

        now = datetime.now()  # current date and time
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")

        return date_time

    @staticmethod
    def create_json_control_file(ctl_file, feedback):
        """Creation and writing of the JSON control file"""

        # Creation of the JSON control file
        theme_uuid = DdrInfo.get_theme_uuid(ctl_file.csz_collection_theme)

        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": ctl_file.download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_theme": theme_uuid
            },
            "service_parameters": [
                {
                    "in_project_filename": Path(ctl_file.out_qgs_project_file_en).name,
                    "language": 'English',
                    "service_schema_name": ctl_file.department
                },
                {
                    "in_project_filename": Path(ctl_file.out_qgs_project_file_fr).name,
                    "language": 'French',
                    "service_schema_name": ctl_file.department
                }
            ]
        }

        # Serialize the JSON
        json_object = json.dumps(json_control_file, indent=4, ensure_ascii=False)

        # Write the JSON document
        ctl_file.control_file_name = os.path.join(ctl_file.control_file_dir, "ControlFile.json")
        with open(ctl_file.control_file_name, "w") as outfile:
            outfile.write(json_object)

        Utils.push_info(feedback, f"INFO: Creation of the JSON control file: {ctl_file.control_file_name}")

        return

    @staticmethod
    def read_csz_themes(ctl_file, feedback):
        """Read the CSZ themes from the service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/czs_themes"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_csz_theme(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_ddr_departments(ctl_file, feedback):
        """Read the DDR departments from the service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_registry_departments"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_ddr_departments(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_user_email(ctl_file, feedback):
        """Read the User Email from the service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_registry_my_publisher_email"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_user_email(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_downloads(ctl_file, feedback):
        """Read the Downloads from the service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_registry_downloads"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_downloads(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_servers(ctl_file, feedback):
        """Read the Servers from the service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_registry_servers"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_servers(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def create_access_token(username, password, ctl_file, feedback):
        """Authentication of the username/password in order to get the access token"""

        url = 'https://qgis.ddr-stage.services.geo.ca/api/login'
        headers = {"accept": "application/json",
                   "Content-type": "application/json",
                   "charset":"utf-8" }

        Utils.push_info(feedback, "INFO: Authentication to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {headers}")
        json_doc = { "password": password,
                     "username": username}

        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.post(url, verify=False, headers=headers, json=json_doc)

            ResponseCodes.create_access_token(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    @staticmethod
    def copy_qgis_project_file(ctl_file, feedback):
        """Creates a copy of the French and English QGIS project files"""

        def read_write_qgs(feedback, qgs_file_name, languange):
            """Read and write the project file in a the temporary folder
               Force project property to be relative path
               Extract the name of the layers
            """

            # Read the QGIS project
            qgs_project = QgsProject.instance()
            qgs_project.read(qgs_file_name)
            qgis_file = Path(qgs_file_name).name
            out_qgs_project_file = os.path.join(ctl_file.control_file_dir, qgis_file)
            qgs_project.write(out_qgs_project_file)  # Write the project in the new directory
            # Force the project properties "Save Paths" to be Relative
            qgs_project.writeEntryBool("Paths", "Absolute", False)
            qgs_project.write(out_qgs_project_file)  # Rewrite the project properties with the new relative path
            Utils.push_info(feedback, "INFO: QGIS project file save as: ", out_qgs_project_file)

            qgs_project = QgsProject.instance()
            for src_layer in qgs_project.mapLayers().values():
                # Adding the name of the layers with the language
                DdrInfo.add_layer(src_layer, languange)

            return out_qgs_project_file

        qgs_project = QgsProject.instance()

        # Validate that the present QGIS project is saved before the processing
        if qgs_project.isDirty():
            raise UserMessageException("The QGIS project file must be saved before starting the DDR publication")

        # Save the name of the actual QGS project file
        ctl_file.src_qgs_project_name = qgs_project.fileName()

        # Create temporary directory
        ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')
        Utils.push_info(feedback, "INFO: Temporary directory created: ", ctl_file.control_file_dir)

        # Clear or Close  the actual QGS project
        qgs_project.clear()

        # Processing the French QGIS project file
        ctl_file.out_qgs_project_file_fr = read_write_qgs(feedback, ctl_file.qgis_project_file_fr, "FR")

        # Processing the English QGIS project file
        ctl_file.out_qgs_project_file_en = read_write_qgs(feedback, ctl_file.qgis_project_file_en, "EN")

    @staticmethod
    def copy_layer_gpkg(ctl_file, feedback):
        """Copy the selected layers in the GeoPackage file"""

        ctl_file.gpkg_file_name = os.path.join(ctl_file.control_file_dir, "qgis_vector_layers.gpkg")
        qgs_project = QgsProject.instance()

        total = DdrInfo.get_nbr_layers()  # Total number of layers to process
        # Loop over each selected layers
        for i, src_layer in enumerate(qgs_project.mapLayers().values()):
            transform_context = QgsProject.instance().transformContext()
            if src_layer.isSpatial():
                if src_layer.type() == QgsMapLayer.VectorLayer:
                    # Only copy vector layer
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.layerName = DdrInfo.get_layer_short_name(src_layer)
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if Path(
                        ctl_file.gpkg_file_name).exists() else QgsVectorFileWriter.CreateOrOverwriteFile
                    options.feedback = None
                    Utils.push_info(feedback, f"INFO: Copying layer: {src_layer.name()} ({str(i+1)}/{str(total)})")

                    error, err1, err2, err3 = QgsVectorFileWriter.writeAsVectorFormatV3(layer=src_layer,
                                              fileName=ctl_file.gpkg_file_name,
                                              transformContext=transform_context,
                                              options=options)

                else:
                    Utils.push_info(feedback, f"WARNING: Layer: {src_layer.name()} is not vector ==> Not transferred")
            else:
                Utils.push_info(feedback, f"WARNING: Layer: {src_layer.name()} is not spatial ==> transferred")

    @staticmethod
    def set_layer_data_source(ctl_file, feedback):

        def _set_layer():

            # Use the newly created GPKG file to set the data source of the QGIS project file
            provider_options = QgsDataProvider.ProviderOptions()
            provider_options.transformContext = qgs_project.transformContext()
            # Loop over each layer
            for i, src_layer in enumerate(qgs_project.mapLayers().values()):
                if src_layer.type() == QgsMapLayer.VectorLayer:
                    # Only process vector layer
                    if src_layer.type() == QgsMapLayer.VectorLayer:

                        qgs_layer_name = src_layer.name()
                        gpkg_layer_name = DdrInfo.get_layer_short_name(src_layer)
                        uri = QgsProviderRegistry.instance().encodeUri('ogr',
                                                                       {'path': ctl_file.gpkg_file_name,
                                                                        'layerName': gpkg_layer_name})
                        src_layer.setDataSource(uri, qgs_layer_name, "ogr", provider_options)

        qgs_project = QgsProject.instance()
        _set_layer()
        qgs_project.write(ctl_file.out_qgs_project_file_en)
        qgs_project.clear()
        if ctl_file.qgis_project_file_fr  != "":
            qgs_project.read(ctl_file.out_qgs_project_file_fr)
            _set_layer()
            qgs_project.write(ctl_file.out_qgs_project_file_fr)

    @staticmethod
    def create_zip_file(ctl_file, feedback):
        """Create the zip file in the working directory"""

        # Change working directory to the temporary directory
        current_dir = os.getcwd()  # Save current directory
        os.chdir(ctl_file.control_file_dir)

        # Create the zip file with the 4 files
        lst_file_to_zip = [Path(ctl_file.control_file_name).name,
                           Path(ctl_file.gpkg_file_name).name,
                           Path(ctl_file.out_qgs_project_file_en).name,
                           Path(ctl_file.out_qgs_project_file_fr).name]
        ctl_file.zip_file_name = os.path.join(ctl_file.control_file_dir, "ddr_publish.zip")
        Utils.push_info(feedback, f"INFO: Creating the zip file: {ctl_file.zip_file_name}")
        with zipfile.ZipFile(ctl_file.zip_file_name, mode="w") as archive:
            for file_to_zip in lst_file_to_zip:
                archive.write(file_to_zip)

        # Reset to the current directory
        os.chdir(current_dir)

    @staticmethod
    def restore_original_project_file(ctl_file, feedback):
        """Restore the original project file"""

        qgs_project = QgsProject.instance()

        # Reopen the original project file
        Utils.push_info(feedback, f"INFO: Restoring original project file (.qgs): {ctl_file.src_qgs_project_name}")
        qgs_project.read(ctl_file.src_qgs_project_name)

    @staticmethod
    def delete_dir_file(ctl_file, feedback):
        """Delete the temporary directory and files"""

        if ctl_file.keep_files == "No":
            # Delete the temporary directory and all its content
            for dummy in range(5):
                # Sometimes the delete does work the first time so we have to retry the file being busy...
                try:
                    shutil.rmtree(ctl_file.control_file_dir)
                    Utils.push_info(feedback, f"INFO: Deleting temporary directory and content: {ctl_file.control_file_dir}")
                    break
                except Exception:
                    # Wait a little bit... to resolve synchronicity problem
                    time.sleep(.5)

    @staticmethod
    def push_info(feedback, message, suppl="", pad_with_dot=False):
        """This method formats and logs the message in the processing toolbox log"""

        str_date_time = Utils.get_date_time()
        suppl = str(suppl)  # Make sure the "text" to display is a string
        lines = suppl.split("\n")  # If the message is on many lines print many lines
        for line in lines:
            if pad_with_dot:
                leading_sp = len(line) - len(line.lstrip())  # Extract the number of leading spaces
                line = line.replace(line[0:leading_sp], "." * leading_sp)  # Replace leading spaces by "." (dots)
            feedback.pushInfo(f"{str_date_time} - {str(message)}{line}")


class ResponseCodes(object):
    """This class manages response codes from the DDR API """

    @staticmethod
    def _push_response(feedback, response, status_code, message):
        """This method displays messages in the log section of the processing tool"""

        try:
            Utils.push_info(feedback, "ERROR: ", f"{status_code} - {message}")
            try:
                json_response = response.json()
                results = json.dumps(json_response, indent=4, ensure_ascii=False)
                Utils.push_info(feedback, "ERROR: ", results, pad_with_dot=True)
            except Exception:
                pass
        except Exception:
            raise UserMessageException(f'JSON response for status code {status_code} is missing or badly formed: {json_response}')

    @staticmethod
    def validate_project_file(feedback, response):
        """This method manages the response codes for the DDR Publisher API Post /validate
        This API validates if a project is compliant when a project is complain it can be published/unpublished"""

        status = response.status_code
        if status == 200:
            json_response = response.json()
            results = json.dumps(json_response, indent=4, ensure_ascii=False)
            Utils.push_info(feedback, "INFO: ", results, pad_with_dot=True)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access token does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def create_access_token(feedback, response):
        """This method manages the response codes for the DDR Publisher API Post /login
        To log into the DDR API and get a valid token"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, "INFO: A token or a refresh token is given to the user")
            json_response = response.json()
            # Store the access token in a global variable for access by other entry points
            LoginToken.set_token(json_response["access_token"])
            expires_in = json_response["expires_in"]
            refresh_token = json_response["refresh_token"]
            refresh_expires_in = json_response["refresh_expires_in"]
            token_type = json_response["token_type"]
            Utils.push_info(feedback, "INFO: ", f"Access token: {LoginToken.get_token(feedback)[0:29]}...")
            Utils.push_info(feedback, "INFO: ", f"Expire in: {expires_in}")
            Utils.push_info(feedback, "INFO: ", f"Refresh token: {refresh_token[0:29]}...")
            Utils.push_info(feedback, "INFO: ", f"Refresh expire in: {refresh_expires_in}")
            Utils.push_info(feedback, "INFO: ", f"Token type: {token_type}")
        elif status == 400:
            ResponseCodes._push_response(feedback, response, 400, "Bad request received on server.")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Invalid credentials provided.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_csz_theme(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /csz_themes
        This method extract the themes from the DDR"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the available Clip Zip Ship Themes."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_themes(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_ddr_departments(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /csz_departments
           This method extract the departments from the DDR"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the available DDR departments."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_departments(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_user_email(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /ddr_my_publisher_email
           This method extract the email associated with user login"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the user email."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_email(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_downloads(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /ddr_registry_downloads
           This method extract the downloads associated with user login"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "The list of DDR Registry Downloads."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_downloads(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_servers(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /ddr_registry_servers
           This method extract the downloads associated with user login"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "The list of DDR Registry Servers."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_servers(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def publish_project_file(feedback, response):
        """This method manages the response codes for the DDR Publisher API PUT /services
        """

        status = response.status_code

        if status == 204:
            msg = "Successfully published the project file(s) in QGIS Server."
            Utils.push_info(feedback, f"INFO: {msg}")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            ResponseCodes._push_response(feedback, response, status, "Unknown error")

    @staticmethod
    def unpublish_project_file(feedback, response):
        """This method manages the response codes for the DDR Unpublisher API DELETE /services
           """

        status = response.status_code

        if status == 204:
            msg = "Successfully unpublished the Service (data remains in the database)."
            Utils.push_info(feedback, f"INFO: {msg}")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            ResponseCodes._push_response(feedback, response, status, "Unknown error")

    @staticmethod
    def update_project_file(feedback, response):
        """This method manages the response codes for the DDR Puplisher API/services
           """

        status = response.status_code

        if status == 204:
            msg = "Successfully updated the data and re-published the project file(s) in QGIS Server."
            Utils.push_info(feedback, f"INFO: {msg}")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            ResponseCodes._push_response(feedback, response, status, "Unknown error")