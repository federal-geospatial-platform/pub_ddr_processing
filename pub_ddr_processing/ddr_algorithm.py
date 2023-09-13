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
import json
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import inspect
import requests
import yaml
from yaml.loader import SafeLoader
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
                       QgsProcessingParameterFile, QgsProcessingParameterDefinition, QgsProcessingParameterBoolean,
                       QgsProcessingOutputString)

PUBLISH = "PUBLISH"
UNPUBLISH = "UNPUBLISH"
UPDATE = "UPDATE"

PUBLICATION_API = "Publication"
REGISTRY_API = "Registry"



@dataclass
class ControlFile:
    """Declare the fields in the control control file"""

    control_file_dir: str = None         # Name of temporary directory
    control_file_name: str = None        # Name of the control file
    core_subject_term: str = None
    download_info_id: str = None
    download_package_file: str = None
    dst_qgs_project_name: str = None     # Name of the output QGIS project file
    email: str = None
    in_project_filename: str = None
    json_document: str = None            # Name of the JSON document
    keep_files: str = None               # Name of the flag to keep the temporary files and directory
    gpkg_layer_counter: int = 0          # Name of the counter of vector layer in the GPKG file
    gpkg_file_name: str = None           # Name of Geopackage containing the vector layers
    language: str = None
    metadata_uuid: str = None
    out_qgs_project_file_en: str = None  # Name out the output English project file
    out_qgs_project_file_fr: str = None  # Name out the output English project file
    qgis_project_file_en: str = None     # Name of the input English QGIS project file
    qgis_project_file_fr: str = None     # Name of the input French QGIS project file
    qgis_server_id: str = None
    service_web: bool = None             # Flag for publishing a web service
    service_download: bool = None        # Flag for publishing a download service
    validate: str = None                 # Is the action in validate mode
    zip_file_name: str = None            # Name of the zip file


class UserMessageException(Exception):
    """Exception raised when a message (likely an error message) needs to be sent to the User."""
    pass


class LoginToken(object):
    """This class manages the login token needed to call the different DDR API end points"""

    # Class variable used to verify that the login class has been set
    __initialization_flag = False

    # Class variable used to store the unique token value of the login
    __token = {}

    @staticmethod
    def set_token(api_name, token):
        """This method sets the token """

        LoginToken.__token[api_name] = token
        LoginToken.__initialization_flag = True

    @staticmethod
    def get_token(api_name, feedback):
        """This method allows to get the token. If the token is None than an error is rose because the login  was
           not done"""

        if not LoginToken.__initialization_flag:
            # The token has hot been initialised (no login)
            Utils.push_info(feedback, f"ERROR: Login first...")
            raise UserMessageException("The user must login first before doing any access to the DDR")

        return LoginToken.__token[api_name]


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
    __json_download_info = []
    __email = None
    __json_downloads = None
    __json_servers = None
    __json_department = None
    __dict_environments = None

    @staticmethod
    def init_project_file():
        """Initialize the variable of the project file"""

        DdrInfo.__qgis_layer_name_en = []
        DdrInfo.__qgis_layer_name_fr = []
        DdrInfo.__short_name_en = []
        DdrInfo.__short_name_fr = []

    @staticmethod
    def add_environment(environment):
        """Add and validate the execution environment"""

        if environment in DdrInfo.__dict_environments:
            DdrInfo.__environment = environment
        else:
            raise UserMessageException(f"The envrionment {environment} is invalid")

    @staticmethod
    def get_http_environment(api_name):
        """Get the http address related to an environment"""

        print (DdrInfo.__dict_environments)
        print (DdrInfo.__dict_environments[DdrInfo.__environment][api_name])
        return DdrInfo.__dict_environments[DdrInfo.__environment][api_name]


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
    def load_config_env_yaml():
        """Load the config file containing the IP address of the servers"""

        # Extract the position
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
        file_path = os.path.join(path, "pub_ddr_processing")
        file_path = os.path.join(file_path, "config_env.yaml")
        with open(file_path, "r") as file:
            yaml_doc = yaml.load(file, Loader=SafeLoader)
            DdrInfo.__dict_environments = yaml_doc["Environment"]
            DdrInfo.__default_environment = yaml_doc["default_env"]

    @staticmethod
    def get_default_environment():
        """Return the default environment"""

        return DdrInfo.__default_environment

    @staticmethod
    def get_environment_lst():
        """Get the list of environment (string of coma separated)"""

        return list(DdrInfo.__dict_environments.keys())

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
        """Add the email associated to the login
           Verify the validity of the JSON structure"""

        # Verify the structure/content of the JSON document
        try:
            DdrInfo.__email = json_email["email"]
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException(f"Issue with the JSON resoponse for the email: {json_email}")

    @staticmethod
    def get_email():
        """Get the email associated to the login"""

        return DdrInfo.__email

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
            raise UserMessageException(f"Issue with the JSON response for the departement: {json_department}")

    @staticmethod
    def get_department_lst():
        """Extract the departments in the form of a list"""

        if DdrInfo.__json_department is not None:
            department_lst = []
            is_attached = None
            for item in DdrInfo.__json_department:
                department = item['qgis_data_store_root_subpath']
                if item.get('is_attached'):
                    is_attached = department
                else:
                    department_lst.append(department)

            # Add the department of the ADMIN (is_attached) in the first position
            if is_attached is not None:
                department_lst.insert(0, is_attached)
        else:
            # Manage the case where the Login is not done and the JSON structure not filed
            department_lst = ["<empty>"]

        return department_lst




    @staticmethod
    def add_download_info(json_download_info):
        """Add the the themes from the JSON response structure
           Verify the validity of the JSON structure"""

        DdrInfo.__json_download_info = json_download_info
        # Verify the structure/content of the JSON document
        try:
            for item in DdrInfo.__json_download_info:
                dummy = item['core_subject_term']  # Just check that the key 'core_subject_term' exist
                dummy = item['department_acrn_en']  # Just check that the key 'department_acrn_en' exist
                dummy = item['download_folder_name']  # Just check that the key 'download_folder_name' exist
                dummy = item['download_folder_path']  # Just check that the key 'download_folder_path' exist
                dummy = item['download_id']  # Just check that the key 'download_id' exist
                dummy = item['metadata_id']  # Just check that the key 'metadata_id_id' exist
                dummy = item['thumbnail_image_file']  # Just check that the key 'thumbnail_image_file' exist

        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException(f"Issue with the JSON response for the download_info: {json_download_info}")

    @staticmethod
    def get_download_info(key_name):
        """Extract a specific field from the JSON document"""

        try:
            for item in DdrInfo.__json_download_info:
                print ("item:", item)
                key_value = item[key_name]
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException(f"Issue with the JSON response for download_info: {DdrInfo.__json_download_info}")

        return key_value

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
            raise UserMessageException(f"Issue with the JSON response for the theme: {json_theme}")

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
            raise UserMessageException(f"Issue with the JSON response for the download: {json_downloads}")

    @staticmethod
    def get_downloads_lst():
        """Extract the departments in the form of a list"""

        if DdrInfo.__json_downloads is not None:
            downloads_lst = []
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
            raise UserMessageException(f"Issue with the JSON response for the server: {json_servers}")

    @staticmethod
    def get_servers_lst():
        """Extract the servers in the form of a list"""

        if DdrInfo.__json_servers is not None:
            servers_lst = []
            for item in DdrInfo.__json_servers:
                id_value = item['id']
                servers_lst.append(id_value)
        else:
            # Manage the case where the Login is not done and the JSON structure not filed
            servers_lst = ["<empty>"]

        return servers_lst


class Utils:
    """Contains a list of static methods"""

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

        if ctl_file.service_download:  # If service download is selected
            # Get the download package name without the extension
            download_package_name = Path(ctl_file.download_package_file).stem
        else:
            download_package_name = ''

        if ctl_file.service_web:  # If service web is selected
            service_parameters =  [
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
        else:
            service_parameters = []


        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_theme": theme_uuid
            },
            "service_parameters": service_parameters
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
    def read_download_info(ctl_file, feedback):
        """Read the CSZ themes from the service end point"""

        url = DdrInfo.get_http_environment()
        print (ctl_file.metadata_uuid)
        url += f"/datasets/metadata_id/{ctl_file.metadata_uuid}"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_download_info(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_csz_themes(ctl_file, feedback):
        """Read the CSZ themes from the service end point"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/czs_themes"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_csz_theme(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_ddr_departments(ctl_file, feedback):
        """Read the DDR departments that the currently logged in User/Publisher has access to
           from the service endpoint"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/ddr_registry_departments"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_ddr_departments(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_user_email(ctl_file, feedback):
        """Read the User Email from the service end point"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/ddr_registry_my_publisher_email"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_user_email(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_downloads(ctl_file, feedback):
        """Read the  downloads that the currently logged in User/Publisher has access to from the service end point"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/ddr_registry_downloads"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_downloads(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_servers(ctl_file, feedback):
        """Read the Servers from the service end point"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/ddr_registry_servers"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_servers(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def create_access_tokens(username, password, ctl_file, feedback):

        def create_one_access_token(api_name):
            """Authentication of the username/password in order to get the access token"""

    #        import web_pdb; web_pdb.set_trace()
            url = DdrInfo.get_http_environment(api_name) + "/login"
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

                ResponseCodes.create_access_token(api_name, feedback, response)

            except requests.exceptions.RequestException as e:
                raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
            return

        create_one_access_token(PUBLICATION_API)

        create_one_access_token(REGISTRY_API)

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
                    ctl_file.gpkg_layer_counter += 1  # Update the counter of vector layer
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
    def copy_download_package_file(process_type, ctl_file, feedback):
        """Copy the download package file in the temp repository
        """

        if process_type in [PUBLISH, UPDATE]:
            # Only copy the download package for publish and update
            download_package_in = Path(ctl_file.download_package_file)
            print ("ctl_file.download_package_file:", ctl_file.download_package_file)
            download_package_name = download_package_in.name
            print ("download_package_name:", download_package_name)
            print ("ctl_file.control_file_dir: ", ctl_file.control_file_dir)
            download_package_out =  os.path.join(ctl_file.control_file_dir, download_package_name)
            shutil.copy(str(download_package_in), download_package_out)

            Utils.push_info(feedback, f"INFO: Copying the download package {ctl_file.download_package_file} in the temp repository {ctl_file.control_file_dir}")
        else:
            # Extract the name of the download package file from the values extracted of the end point
            # ctl_file.download_package_file = DdrInfo.get_download_info('download_folder_name') + ".zip"
            ctl_file.download_package_file = ""



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

        # Create the zip file
        lst_file_to_zip = [Path(ctl_file.control_file_name).name]

        #Append the needed files
        if ctl_file.service_web:  # The service web is selected
            lst_file_to_zip.append(Path(ctl_file.out_qgs_project_file_en).name)
            lst_file_to_zip.append(Path(ctl_file.out_qgs_project_file_fr).name)
        if ctl_file.gpkg_layer_counter >= 1:
            # Add the GPKG file to the ZIP file if vector layers are present
            lst_file_to_zip.append(Path(ctl_file.gpkg_file_name).name)
        if ctl_file.download_package_file is not None:  # The service download is selected
            if ctl_file.download_package_file != "":
                lst_file_to_zip.append(Path(ctl_file.download_package_file).name)
            
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

    @staticmethod
    def get_core_subject_term():
        """Get the core subject terms from a json file and return a list"""
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
        file_path = os.path.join(path, "pub_ddr_processing")
        file_path = os.path.join(file_path, "core_subject_term.json")
        with open(file_path) as file:
            cst = json.load(file)
            return cst["core_subject_term"]

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
            print ("reponse: ", json_response)
            results = json.dumps(json_response, indent=4, ensure_ascii=False)
            Utils.push_info(feedback, "INFO: ", "200 - Validation is successful")
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
    def create_access_token(api_name, feedback, response):
        """This method manages the response codes for the DDR Publisher API Post /login
        To log into the DDR API and get a valid token"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, "INFO: A token or a refresh token is given to the user")

            Utils.push_info(feedback, "INFO: ", f"JSON Response: {str(response.text)}...")

            json_response = response.json()
            # Store the access token in a global variable for access by other entry points
            LoginToken.set_token(api_name, json_response["access_token"])
            expires_in = json_response["expires_in"]
            refresh_token = json_response["refresh_token"]
            refresh_expires_in = json_response["refresh_expires_in"]
            token_type = json_response["token_type"]
            Utils.push_info(feedback, "INFO: ", f"Access token: {LoginToken.get_token(api_name, feedback)[0:29]}...")
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
    def read_download_info(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /csz_themes
        This method extract the themes from the DDR"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading dataset info based on a given dataset UUID."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DdrInfo.add_download_info(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 404:
            ResponseCodes._push_response(feedback, response, 404, "The requested URI was not found..")
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
        """This method manages the response codes for the DDR Publisher API Get /ddr_my_email
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
        """This method manages the response codes for the DDR Publisher API Get /ddr_downloads
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
        """This method manages the response codes for the DDR Publisher API Get /ddr_servers
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


class UtilsGui():
    """Contains a list of static methods"""

    HELP_USAGE = """
        <b>Usage</b>
        <u>Select the validation type</u>: <i>Publish</i>: For the publication of a collection; <i>Unpublish</i>: For deleting a collection; <i>Update</i>: For updating an existing collection.  
        <u>Select the English QGIS project file (.qgs)</u>: Select the project file with the ENGLISH layer description.
        <u>Select the French QGIS project file (.qgs)</u>: Select the project file with the French layer description.
        <u>Select the department</u>: Select which department own the publication.
        <u>Enter the metadata UUID</u>: Enter the UUID associated to this UUID.
        <u>Select the CZS theme</u>: Select the theme under which the project will be published in the clip zip ship (CZS)
        <u>Select the download info ID</u>: Download ID info.
        <u>Select the web server</u>: Name of the QGIS server used for the publication.
        <u>Select the download package file</u>: Select the download package file to upload on the FTP. (optional)
        <u>Select a core subject term</u>: Select a core subject term, mandatory for uploading a download package otherwise the parameter is optional.
        <b>Advanced Parameters</b>
        <u>Enter your email address</u>: Email address used to send publication notification.
        <u>Keep temporary files (for debug purpose)</u> : Flag (Yes/No) for keeping/deleting temporary files.
        <u>Select execution environment (should be production)</u> : Name of the execution environment. 
        <b>Note All parameters may not apply to each <i>Publish, Unpublish, Update, Validate</i> process.</b>
    """

    @staticmethod
    def add_login(self):
        """Add Login menu"""

        self.addParameter(
            QgsProcessingParameterAuthConfig('AUTHENTICATION', \
                'Select a DDR Publication Authentication Configuration or create a new one', defaultValue=None))

    @staticmethod
    def add_web_service(self, action):
        """Add Select the check box for the web service"""

        parameter = (QgsProcessingParameterBoolean(
            name='SERVICE_WEB',
            description=self.tr(f"{action} a web service"),
            defaultValue=False,
            optional=False))
        parameter.setHelp(f"Check the box if you which to {action} a web service and fill the section 'Web service parameters'")

        self.addParameter(parameter)

    @staticmethod
    def add_download_service(self, action):
        """Add Select the check box for the download service"""

        parameter = (QgsProcessingParameterBoolean(
            name='SERVICE_DOWNLOAD',
            description=self.tr(f"{action} a download service"),
            defaultValue=False,
            optional=False))
        parameter.setHelp(f"Check the box if you which to {action} a download service and fill the section 'Download service parameters'")

        self.addParameter(parameter)

    @staticmethod
    def add_validation_type(self):
        """Add Select the the type of validation"""

        lst_validation_type = ["Publish", "Update", "Unpublish"]
        self.addParameter(QgsProcessingParameterEnum(
            name='VALIDATION_TYPE',
            description=self.tr("Select the validation type"),
            options=lst_validation_type,
            defaultValue=lst_validation_type[0],
            usesStaticStrings=True,
            optional=False,
            allowMultiple=False))

    @staticmethod
    def add_qgis_file(self, message):
        """Add Select EN and FR project file menu"""

        parameter = QgsProcessingParameterFile(
                name='QGIS_FILE_EN',
                description='<hr><br><b>Web service parameters</b><br><br>Select the English QGIS project file (.qgs)',
                extension='qgs',
                optional=True,
                behavior=QgsProcessingParameterFile.File)
        parameter.setHelp(message)
        self.addParameter(parameter)

        parameter = QgsProcessingParameterFile(
                name='QGIS_FILE_FR',
                description=' Select the French QGIS project file (.qgs)',
                extension='qgs',
                optional=True,
                behavior=QgsProcessingParameterFile.File)
        parameter.setHelp(message)
        self.addParameter(parameter)



    @staticmethod
    def add_department(self):
        """Add Select department menu"""

        department_lst = DdrInfo.get_department_lst()
        self.addParameter(QgsProcessingParameterEnum(
            name='DEPARTMENT',
            description=self.tr("<br><b>General parameters</b><br><br>Select the department"),
            options=department_lst,
            defaultValue=department_lst[0],
            usesStaticStrings=True,
            optional=False,
            allowMultiple=False))

    @staticmethod
    def add_uuid(self):
        """Add Select UUID menu"""

        str_uuid = ""
#        import uuid
#        str_uuid = uuid.uuid4()
        self.addParameter(QgsProcessingParameterString(
            name="METADATA_UUID",
            defaultValue=str(str_uuid),
            optional=False,
            description=self.tr('Enter the metadata UUID')))

    @staticmethod
    def add_download_info(self, message):
        """Add Select download info menu"""

        lst_download_info_id = DdrInfo.get_downloads_lst()
        parameter = QgsProcessingParameterEnum(
            name='DOWNLOAD_INFO_ID',
            description=self.tr("Select the download server"),
            options=lst_download_info_id,
            defaultValue=lst_download_info_id[0],
            usesStaticStrings=True,
            optional=True,
            allowMultiple=False)
        parameter.setHelp(message)
        self.addParameter(parameter)


    @staticmethod
    def add_email(self):
        """Add Select email menu"""

        parameter = QgsProcessingParameterString(
            name="EMAIL",
            optional=False,
            defaultValue=str(DdrInfo.get_email()),
            description=self.tr('Enter your email address'))
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_validate(self, action):
        """Add Validate check box"""


        parameter = (QgsProcessingParameterBoolean(
            name='Validate',
            description=self.tr(f"Only validate the {action} action"),
            defaultValue=False,
            optional=False))
        parameter.setHelp(f"In validate mode, the input parameters are validated and no action is performed ")
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_qgs_server_id(self, message):
        """Add Select server menu"""

        lst_qgs_server_id = DdrInfo.get_servers_lst()
        parameter = QgsProcessingParameterEnum(
            name='QGS_SERVER_ID',
            description=self.tr('Select the web server'),
            options=lst_qgs_server_id,
            defaultValue="DDR_QGS1",
            usesStaticStrings=True,
            optional=True,
            allowMultiple=False)
        parameter.setHelp(message)
        self.addParameter(parameter)

    @staticmethod
    def add_csz_themes(self, message):
        """Add Select themes menu"""

        parameter = QgsProcessingParameterEnum(
            name='CSZ_THEMES',
            description=self.tr("Select the Clip-Zip-Ship (CSZ) theme"),
            options=[""] + DdrInfo.get_theme_lst("en"),
            usesStaticStrings=True,
            allowMultiple=False,
            optional=True)
        parameter.setHelp(message)
        self.addParameter(parameter)

    @staticmethod
    def add_keep_files(self):
        """Add Keep file menu"""

        lst_flag = ['Yes', 'No']
        parameter = QgsProcessingParameterEnum(
            name='KEEP_FILES',
            description=self.tr('Keep temporary files (for debug purpose)'),
            options=lst_flag,
            defaultValue=lst_flag[1],
            usesStaticStrings=True,
            optional=False,
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_environment(self):
        """Add Select environment menu"""

        DdrInfo.load_config_env_yaml()
        parameter = QgsProcessingParameterEnum(
            name='ENVIRONMENT',
            description=self.tr('Select execution environment (should be production)'),
            options=DdrInfo.get_environment_lst(),
            defaultValue=DdrInfo.get_default_environment(),
            usesStaticStrings=True,
            allowMultiple=False)
        # parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def read_parameters(self, ctl_file, parameters, context):

        ctl_file.service_web = self.parameterAsBool(parameters, 'SERVICE_WEB', context)
        ctl_file.service_download = self.parameterAsBool(parameters, 'SERVICE_DOWNLOAD', context)
        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
        ctl_file.metadata_uuid = self.parameterAsString(parameters, 'METADATA_UUID', context)
        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
        ctl_file.keep_files = self.parameterAsString(parameters, 'KEEP_FILES', context)
        ctl_file.csz_collection_theme = self.parameterAsString(parameters, 'CSZ_THEMES', context)
        ctl_file.qgis_project_file_en = self.parameterAsString(parameters, 'QGIS_FILE_EN', context)
        ctl_file.qgis_project_file_fr = self.parameterAsString(parameters, 'QGIS_FILE_FR', context)
        ctl_file.validate = self.parameterAsBool(parameters, 'VALIDATE', context)
        ctl_file.core_subject_term = self.parameterAsString(parameters, 'CORE_SUBJECT_TERM', context)
        ctl_file.download_package_file = self.parameterAsString(parameters, 'DOWNLOAD_PACKAGE', context)
        if ctl_file.download_package_file =='':
            ctl_file.download_package_file = None

    @staticmethod
    def add_download_package(self, message):
        """Add Download package file selector to menu"""

        parameter = QgsProcessingParameterFile(
            name='DOWNLOAD_PACKAGE',
            description=self.tr('<hr><br><b>Download service parameters</b><br><br>Select the download package file (.zip)'),
            behavior=QgsProcessingParameterFile.File,
            extension="zip",
            optional=True,
            defaultValue=None)
        parameter.setHelp(message)
        self.addParameter(parameter)

    @staticmethod
    def add_core_subject_term(self, message):

        parameter = QgsProcessingParameterEnum(
            name="CORE_SUBJECT_TERM",
            description=self.tr('Select the appropriate core subject term'),
            options=Utils.get_core_subject_term(),
            usesStaticStrings=True,
            allowMultiple=False,
            optional=True,
            defaultValue=None)
        parameter.setHelp(message)
        # parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

def dispatch_algorithm(self, process_type, parameters, context, feedback):

    # Init the project files by resetting the layers structures
    DdrInfo.init_project_file()

    # Create the control file data structure
    ctl_file = ControlFile()

    # Extract the parameters
    UtilsGui.read_parameters(self, ctl_file, parameters, context)

    print (process_type, UNPUBLISH)
    if process_type == UNPUBLISH:
        # Extract specific information related to Unpublish a Web service

        if ctl_file.service_web:
            pass
#        if ctl_file.service_download:
#            Utils.read_download_info(ctl_file, feedback)

    # Create temporary directory
    ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')
    Utils.push_info(feedback, "INFO: Temporary directory created: ", ctl_file.control_file_dir)

    if ctl_file.service_web:  # if web_service is selected
        # Copy the QGIS project file (.qgs)
        Utils.copy_qgis_project_file(ctl_file, feedback)

        # Copy the selected layers in the GPKG file
        Utils.copy_layer_gpkg(ctl_file, feedback)

        # Set the layer data source
        Utils.set_layer_data_source(ctl_file, feedback)

    if ctl_file.service_download:  # if download service is selected
        print("Service download in:", ctl_file.service_download)
        # Copy the download package file in temp repository
        Utils.copy_download_package_file(process_type, ctl_file, feedback)

    # Creation of the JSON control file
    Utils.create_json_control_file(ctl_file, feedback)

    # Creation of the ZIP file
    Utils.create_zip_file(ctl_file, feedback)

    # Validate the project file
    if ctl_file.validate:
        # The action is executed in validate mode
        DdrValidateService.validate_project_file(ctl_file, process_type, parameters, context, feedback)
    elif process_type == PUBLISH:
        # Publish the project file
        DdrPublishService.publish_project_file(ctl_file, parameters, context, feedback)
    elif process_type == UNPUBLISH:
        # Unpublish the project file
        DdrUnpublishService.unpublish_project_file(ctl_file, parameters, context, feedback)
    elif process_type == "UPDATE":
        # Update the project file
        DdrUpdateService.update_project_file(ctl_file, parameters, context, feedback)
    else:
        raise UserMessageException(f"Internal error. Unknown Process Type: {process_type}")

    if ctl_file.service_web:  # if web_service is selected
        # Restoring original .qgs project file
        Utils.restore_original_project_file(ctl_file, feedback)

    # Deleting the temporary directory and files
    # import web_pdb; web_pdb.set_trace()
    Utils.delete_dir_file(ctl_file, feedback)

    return


class DdrPublishService(QgsProcessingAlgorithm):
    """Main class defining how to publish a service.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrPublishService()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'publish_service'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Publish a service')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading | QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.Available

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This processing plugin publishes the geospatial layers stored in .qgs project files (FR and EN) to the DDR repository. \
    It can only publish vector layers but the layers can be stored in any format supported by QGIS (e.g. GPKG, \
    SHP, PostGIS, ...).  The style, service information, metadata stored in the .qgs project file will follow. \
    Also, it will upload files to an FTP when a download package file is selected as well as a core subject term.\
    A message is displayed in the log and an email is sent to the user informing the latter on the status of \
    the publication. 
        
        """

        help_str += help_str + UtilsGui.HELP_USAGE

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        # General parameters
        action = "Publish"
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_web_service(self, action)
        UtilsGui.add_download_service(self, action)

        # Web service parameters
        message = "Mandatory if you choose to publish a web service"
        message_opt = "Optional even if you choose to publish a web service"
        UtilsGui.add_qgis_file(self, message)
        UtilsGui.add_csz_themes(self, message_opt)
        UtilsGui.add_qgs_server_id(self, message)

        # Download service parameters
        message = "Mandatory if you choose to publish a download service"
        UtilsGui.add_download_package(self, message)
        UtilsGui.add_core_subject_term(self, message)
        UtilsGui.add_download_info(self, message)

        # Advanced parameters
        action = "publish"
        UtilsGui.add_email(self)
        UtilsGui.add_keep_files(self)
        UtilsGui.add_validate(self, action)



#    def read_parameters(self, ctl_file, parameters, context, feedback):
#        """Reads the different parameters in the form and stores the content in the data structure"""
#
#        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)
#        print ("read parameters")
#        0/0

        return

    def checkParameterValues(self, parameters, context):
        """Check if the selection of the input parameters is valid"""

        # Create the control file data structure
        control_file = ControlFile()

        UtilsGui.read_parameters(self, control_file, parameters, context )

        # At least Web Service or Download Service check box must be selected
        if not control_file.service_web and not control_file.service_download:
            message = "You must at least select one of the following service:\n"
            message += "   - Publish web service\n"
            message += "   - Publish download service"
            return (False, message)

        # If Web service is selected some web parameters must be selected
        if control_file.service_web:
            if control_file.qgis_project_file_en == "" or \
                control_file.qgis_project_file_fr == "" or \
                control_file.qgis_server_id == "":
                message = "When selecting Publish web service, you must fill the following parameters: \n"
                message += "   - Select the English QGIS project file \n"
                message += "   - Select the French QGIS project file \n"
                message += "   - Select the web server"
                return (False, message)
        else:
            if control_file.qgis_project_file_en != "" or \
                control_file.qgis_project_file_fr != "":
                message = "Publish a web service is not selected, the following parameters must be empty: \n"
                message += "   - Select the English QGIS project file \n"
                message += "   - Select the French QGIS project file"
                return (False, message)

        # If Download service is selected some download parameters must be selected
        if control_file.service_download:
            if control_file.download_package_file== "" or \
                    control_file.core_subject_term == "" or \
                    control_file.download_info_id == "":
                message = "When selecting publish download service, you must fill the following parameters: \n"
                message += "   - Select the download package file \n"
                message += "   - Select the appropriate core subject term \n"
                message += "   - Select the download server"
                return (False, message)
        else:
            if control_file.download_package_file!= "":
                message = "Publish a download service is not selected, the following parameter must be empty: \n"
                message += "   - Select the download package file"
                return (False, message)

        return (True, "")

    @staticmethod
    def publish_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/publish"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        Utils.push_info(feedback, f"INFO: Publishing to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file to publish: {ctl_file.zip_file_name}")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        try:
            response = requests.put(url, files=files, verify=False, headers=headers)
            ResponseCodes.publish_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            dispatch_algorithm(self, "PUBLISH", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Publish process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}


class DdrUpdateService(QgsProcessingAlgorithm):
    """Main class defining how to update a service..
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrUpdateService()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'update_service'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Update a service')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading | QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.Available

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This processing plugin updates the geospatial layers stored in .qgs project files (FR and EN) to the DDR repository. \
    It can only update vector layers but the layers can be stored in any format supported by QGIS (e.g. GPKG, \
    SHP, PostGIS, ...).  The style, service information, metadata stored in the .qgs project can be updated. \
    Also, it will update the files on the FTP if a download package file is selected as well as a core subject term. \
    A message is displayed in the log and an email is sent to the user informing the latter on the status of \
    the publication. 

        """

        help_str += help_str + UtilsGui.HELP_USAGE

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        UtilsGui.add_qgis_file(self, "")
        UtilsGui.add_department(self)
#        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self, "")
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self,"")
        UtilsGui.add_qgs_server_id(self, "")
        UtilsGui.add_keep_files(self)
        UtilsGui.add_download_package(self, "")
        UtilsGui.add_core_subject_term(self, "")

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def update_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = DdrInfo.get_http_environment()
        url += "/update"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        Utils.push_info(feedback, f"INFO: Pushing updates to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file to update: {ctl_file.zip_file_name}")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        try:
            response = requests.patch(url, files=files, verify=False, headers=headers)
            ResponseCodes.update_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            dispatch_algorithm(self, "UPDATE", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Update process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}


class DdrValidateService(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrValidateService()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'validate_service'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Validate a service')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading | QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.Available

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This processing plugin validates the content of a QGIS project files (.qgs) FR and EN. If the validation \
    pass, the project can be publish, update or unpublish to the DDR repository. If the validation fails, \
    you must edit the QGIS  and rerun the validation. This plugin does not write anything into the QGIS \
    server so you can rerun it safely until there is no error and than run the appropriate tool (publish, \
    unpublish or update). """

        help_str += help_str + UtilsGui.HELP_USAGE

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        UtilsGui.add_validation_type(self)
        UtilsGui.add_qgis_file(self, "")
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self, "")
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self, "")
        UtilsGui.add_qgs_server_id(self, "")
        UtilsGui.add_keep_files(self)
        UtilsGui.add_download_package(self, "")
        UtilsGui.add_core_subject_term(self, "")

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def validate_project_file(ctl_file, process_type, parameters, context, feedback):
        """"""

#        import web_pdb; web_pdb.set_trace()
        print ("Process type:", process_type.lower())
        process_type = "publish"
        url = DdrInfo.get_http_environment(PUBLICATION_API)
        url += "/validate"
        headers = {'accept': 'application/json',
                   'charset': 'utf-8',
                   'Authorization': 'Bearer ' + LoginToken.get_token(PUBLICATION_API, feedback)
                   }
        data = {
            'operation': process_type.lower()
        }
        files = {
            'zip_file': open(ctl_file.zip_file_name, 'rb')
        }
        print (headers)

        Utils.push_info(feedback, "INFO: Validating project")
        Utils.push_info(feedback, "INFO: HTTP Headers: ", headers)
        Utils.push_info(feedback, "INFO: Zip file to publish: ", ctl_file.zip_file_name)

        try:
            Utils.push_info(feedback, "INFO: HTTP Post Request: ", url)
            response = requests.post(url, files=files, verify=False, headers=headers, data=data)
            ResponseCodes.validate_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            dispatch_algorithm(self, "VALIDATE", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Validate process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}


class DdrUnpublishService(QgsProcessingAlgorithm):
    """Main class defining the Unpublish algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrUnpublishService()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'unpublish_service'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Unpublish a service')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading | QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.Available

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin removes the content of a QGIS project file (.qgs) stored to the DDR repository. \
                      It will also remove the files on the FTP if a download package file is selected as well as a core subject term. \
                   """

        help_str += help_str + UtilsGui.HELP_USAGE

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        # General parameters
        action = 'Unpublish'
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_web_service(self, action)
        UtilsGui.add_download_service(self, action)

#        # Web service parameters
#        message = "Mandatory if you choose to unpublish a web service"
#        message_opt = "Optional even if you choose to upublish a web service"
#        UtilsGui.add_qgis_file(self, message)
#        UtilsGui.add_csz_themes(self, message_opt)
#        UtilsGui.add_qgs_server_id(self, message)
#
#        # Download service parameters
#        message = "Mandatory if you choose to unpublish a download service"
#        UtilsGui.add_download_package(self, message)
#        UtilsGui.add_core_subject_term(self, message)
#        UtilsGui.add_download_info(self, message)

        # Advanced parameters
        action = "unpublish"
        UtilsGui.add_email(self)
        UtilsGui.add_keep_files(self)
        UtilsGui.add_validate(self, action)

#    def read_parameters(self, ctl_file, parameters, context, feedback):
#        """Reads the different parameters in the form and stores the content in the data structure"""
#
#        UtilsGui.read_parameters(self, ctl_file, parameters, context)
#
#        return

    @staticmethod
    def unpublish_project_file(ctl_file, parameters, context, feedback):
        """Unpublish a QGIS project file """

        url = DdrInfo.get_http_environment(REGISTRY_API)
        url += "/unpublish"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(REGISTRY_API, feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}
        Utils.push_info(feedback, f"INFO: Unpublishing data from the DDR")
        Utils.push_info(feedback, f"INFO: HTTP Delete Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file sent to unpublish process: {ctl_file.zip_file_name}")

        try:
            response = requests.delete(url, files=files, verify=False, headers=headers)
            ResponseCodes.unpublish_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def checkParameterValues(self, parameters, context):
        """Check if the selection of the input parameters is valid
        """

        # Create the control file data structure
        control_file = ControlFile()

        UtilsGui.read_parameters(self, control_file, parameters, context )

        # At least Web Service or Download Service check box must be selected
        if not control_file.service_web and not control_file.service_download:
            message = "You must at least select one of the following service:\n"
            message += "   - Unpublish web service\n"
            message += "   - Unpublish download service"
            return False, message

        return True, ""

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """
        try:
            dispatch_algorithm(self, UNPUBLISH, parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Unpublish process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}


class DdrLogin(QgsProcessingAlgorithm):
    """Main class defining the DDR Login algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrLogin()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'login'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading | QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.Available

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Login')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """

        return ''
#        return 'Authentication (first step)'

#    def flags(self):
#
#        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin logs into the DDR repository server. The authentication operation is \
        mandatory before  doing any management operation: publish, update, unpublish or validate. 
        """

        help_str = help_str + UtilsGui.HELP_USAGE

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        UtilsGui.add_login(self)
        UtilsGui.add_environment(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

#        import web_pdb; web_pdb.set_trace()
        auth_method = self.parameterAsString(parameters, 'AUTHENTICATION', context)
        environment = self.parameterAsString(parameters, 'ENVIRONMENT', context)
        print ("Environment: ", environment)
        Utils.push_info(feedback, f"INFO: Execution environment: {environment}")
        DdrInfo.add_environment(environment)


#        authMgr = QgsApplication.authManager()
#        if authMgr.authenticationDatabasePath():
#            # already initialized => we are inside a QGIS app.
#            if authMgr.masterPasswordIsSet():
#                msg = 'Authentication master password not recognized'
#                assert authMgr.masterPasswordSame("MasterPass123$"), msg
#                Utils.push_info(feedback, f"INFO: Code 1")
#            else:
#                msg = 'Master password could not be set'
#                # The verify parameter checks if the hash of the password was
#                # already saved in the authentication db
#        authMgr.setMasterPassword("MasterPass123$", verify=True)
#                Utils.push_info(feedback, f"INFO: Code 2")
#        else:
#            # outside qgis, e.g. in a testing environment => setup env var before
#            # db init
#            os.environ['QGIS_AUTH_DB_DIR_PATH'] = "/path/where/located/qgis-auth.db"
#            msg = 'Master password could not be set'
#           assert authMgr.setMasterPassword("your master password", True), msg
#            authMgr.init("/path/where/located/qgis-auth.db")
#            Utils.push_info(feedback, f"INFO: Code 3")

#        cfg = QgsAuthMethodConfig()
#        cfg.setMethod("Basic")
#        cfg.setName("mergin4")
#        cfg.setConfig("username", "pil123456")
#        cfg.setConfig("password", "a123456")
#        cfg.setId("p3m9sdd")
#        auth_manager = QgsApplication.authManager()
#        auth_manager.storeAuthenticationConfig(cfg)
#        cfg.id()
#        Utils.push_info(feedback, f"INFO: Grapped config ID: {str(cfg.id())}")


        # Enable the extraction of the password when working in the testing or mocking environment
        if environment == "Testing":
            authMgr = QgsApplication.authManager()
            authMgr.setMasterPassword("MasterPass123$", verify=True)


        # Get the application's authentication manager
        auth_mgr = QgsApplication.authManager()

        # Create an empty QgsAuthMethodConfig object
        auth_cfg = QgsAuthMethodConfig()

        # Load config from manager to the new config instance and decrypt sensitive data
        auth_mgr.loadAuthenticationConfig(auth_method, auth_cfg, True)

        # Get the configuration information (including username and password)
        auth_cfg.configMap()
        auth_info = auth_cfg.configMap()

        try:
            username = auth_info['username']
            password = auth_info['password']
        except KeyError:
            raise UserMessageException("Unable to extract username/password from QGIS "
                                       "authentication system")

        Utils.push_info(feedback, f"INFO: Username: {username}")
        Utils.push_info(feedback, f"INFO: Username: {password}")
        return username, password

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            # Create the control file data structure
            ctl_file = ControlFile()
            (username, password) = self.read_parameters(ctl_file, parameters, context, feedback)

            # Create the access tokens needed for the API call
            Utils.create_access_tokens(username, password, ctl_file, feedback)

            Utils.read_csz_themes(ctl_file, feedback)
            Utils.read_ddr_departments(ctl_file, feedback)
            Utils.read_user_email(ctl_file, feedback)
#            import web_pdb; web_pdb.set_trace()
            Utils.read_downloads(ctl_file, feedback)
            Utils.read_servers(ctl_file, feedback)

        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Login process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}
