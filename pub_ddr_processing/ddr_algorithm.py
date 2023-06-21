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
import inspect
import requests
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
from .Utils import ControlFile, UserMessageException, DdrInfo, LoginToken, Utils, ResponseCodes


class UtilsGui():
    """Contains a list of static methods"""

    HELP_USAGE = """
        <b>Usage</b>
        <u>Select the validation type</u>: <i>Publish</i>: For the publication of a collection; <i>Unpublish</i>: For deleting a collection; <i>Republish</i>: For updating an existing collection.  
        <u>Select the English QGIS project file (.qgs)</u>: Select the project file with the ENGLISH layer description.
        <u>Select the French QGIS project file (.qgs)</u>: Select the project file with the French layer description.
        <u>Select the department</u>: Select which department own the publication.
        <u>Enter the metadata UUID</u>: Enter the UUID associated to this UUID.
        <u>Select the CZS theme</u>: Select the theme under which the project will be published in the clip zip ship (CZS)
        <u>Select the download info ID</u>: Download ID info (no choice).
        <u>Select the QGIS server</u>: Name of the QGIS server used for the publication (no choice).
        <b>Advanced Parameters</b>
        <u>Enter your email address</u>: Email address used to send publication notification.
        <u>Keep temporary files (for debug purpose)</u> : Flag (Yes/No) for keeping/deleting temporary files.
        <u>Select execution environment (should be production)</u> : Name of the execution environment. 
        <b>Note All parameters may not apply to each <i>Publish, Unpublish, Republish, Validate</i> process.</b>
    """

    @staticmethod
    def add_login(self):
        """Add Login menu"""

        self.addParameter(
            QgsProcessingParameterAuthConfig('AUTHENTICATION', 'Authentication Configuration', defaultValue=None))

    @staticmethod
    def add_validation_type(self):
        """Add Select the the type of validation"""

        lst_validation_type = ["Publish", "Republish", "Unpublish"]
        self.addParameter(QgsProcessingParameterEnum(
            name='VALIDATION_TYPE',
            description=self.tr("Select the validation type"),
            options=lst_validation_type,
            defaultValue=lst_validation_type[0],
            usesStaticStrings=True,
            allowMultiple=False))

    @staticmethod
    def add_qgis_file(self):
        """Add Select EN and FR project file menu"""

        self.addParameter(
            QgsProcessingParameterFile(
                name='QGIS_FILE_EN',
                description=' Select the English QGIS project file (.qgs)',
                extension='qgs',
                behavior=QgsProcessingParameterFile.File))

        self.addParameter(
            QgsProcessingParameterFile(
                name='QGIS_FILE_FR',
                description=' Select the French QGIS project file (.qgs)',
                extension='qgs',
                behavior=QgsProcessingParameterFile.File))

    @staticmethod
    def add_department(self):
        """Add Select department menu"""

        self.addParameter(QgsProcessingParameterEnum(
            name='DEPARTMENT',
            description=self.tr("Select the department"),
            options=DdrInfo.get_department_lst(),
            defaultValue="nrcan",
            usesStaticStrings=True,
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
            description=self.tr('Enter the metadata UUID')))

    @staticmethod
    def add_download_info(self):
        """Add Select download info menu"""

        lst_download_info_id = DdrInfo.get_downloads_lst()
        self.addParameter(QgsProcessingParameterEnum(
            name='DOWNLOAD_INFO_ID',
            description=self.tr("Select the download info ID"),
            options=lst_download_info_id,
            defaultValue=lst_download_info_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

    @staticmethod
    def add_email(self):
        """Add Select email menu"""

        parameter = QgsProcessingParameterString(
            name="EMAIL",
            defaultValue=str(DdrInfo.get_email()),
            description=self.tr('Enter your email address'))
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_qgs_server_id(self):
        """Add Select server menu"""

        lst_qgs_server_id = DdrInfo.get_servers_lst()
        self.addParameter(QgsProcessingParameterEnum(
            name='QGS_SERVER_ID',
            description=self.tr('Select the QGIS server'),
            options=lst_qgs_server_id,
            defaultValue=lst_qgs_server_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

    @staticmethod
    def add_csz_themes(self):
        """Add Select themes menu"""

        self.addParameter(QgsProcessingParameterEnum(
            name='CSZ_THEMES',
            description=self.tr("Select the Clip-Zip-Ship (CSZ) theme:"),
            options=[""] + DdrInfo.get_theme_lst("en"),
            usesStaticStrings=True,
            allowMultiple=False,
            optional=True))

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
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_environment(self):
        """Add Select environment menu"""

        lst_flag = ['Production', 'Staging', 'Testing']
        parameter = QgsProcessingParameterEnum(
            name='ENVIRONMENT',
            description=self.tr('Select execution environment (should be production)'),
            options=lst_flag,
            defaultValue=lst_flag[0],
            usesStaticStrings=True,
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def read_parameters(self, ctl_file, parameters, context, feedback):

        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
        ctl_file.metadata_uuid = self.parameterAsString(parameters, 'METADATA_UUID', context)
        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
        ctl_file.keep_files = self.parameterAsString(parameters, 'KEEP_FILES', context)
        ctl_file.csz_collection_theme = self.parameterAsString(parameters, 'CSZ_THEMES', context)
        ctl_file.qgis_project_file_en = self.parameterAsString(parameters, 'QGIS_FILE_EN', context)
        ctl_file.qgis_project_file_fr = self.parameterAsString(parameters, 'QGIS_FILE_FR', context)
        ctl_file.validation_type = self.parameterAsString(parameters, 'VALIDATION_TYPE', context)


def dispatch_algorithm(self, process_type, parameters, context, feedback):

    # Init the project files by resetting the layers structures
    DdrInfo.init_project_file()

    # Create the control file data structure
    ctl_file = ControlFile()

    # Extract the parameters
    self.read_parameters(ctl_file, parameters, context, feedback)

    # Copy the QGIS project file (.qgs)
    Utils.copy_qgis_project_file(ctl_file, feedback)

    # Copy the selected layers in the GPKG file
    Utils.copy_layer_gpkg(ctl_file, feedback)

    # Set the layer data source
    Utils.set_layer_data_source(ctl_file, feedback)

    # Creation of the JSON control file
    Utils.create_json_control_file(ctl_file, feedback)

    # Creation of the ZIP file
    Utils.create_zip_file(ctl_file, feedback)

    # Validate the project file
    if process_type == "VALIDATE":
        DdrValidate.validate_project_file(ctl_file, parameters, context, feedback)
    elif process_type == "PUBLISH":
        # Publish the project file
        DdrPublish.publish_project_file(ctl_file, parameters, context, feedback)
    elif process_type == "UNPUBLISH":
        # Unpublish the project file
        DdrUnpublish.unpublish_project_file(ctl_file, parameters, context, feedback)
    elif process_type == "UPDATE":
        # Update the project file
        DdrUpdate.update_project_file(ctl_file, parameters, context, feedback)
    else:
        raise UserMessageException(f"Internal error. Unknown Process Type: {process_type}")

    # Restoring original .qgs project file
    Utils.restore_original_project_file(ctl_file, feedback)

    # Deleting the temporary directory and files
    # import web_pdb; web_pdb.set_trace()
    Utils.delete_dir_file(ctl_file, feedback)

    return


class DdrPublish(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrPublish()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'publish'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Publish Project')

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

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This plugin publishes the geospatial layers stored in .qgs project files (FR and EN) to the DDR repository. \
    It can only publish vector layers but the layers can be stored in any format supported by QGIS (e.g. GPKG, \
    SHP, PostGIS, ...).  The style, service information, metadata stored in the .qgs project file will follow. \
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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def publish_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = DdrInfo.get_http_environment()
        url += "/api/publish"
        #url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
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


class DdrUpdate(QgsProcessingAlgorithm):
    """Main class defining the Update algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrUpdate()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'update'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Republish Project')

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

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This plugin publishes the geospatial layers stored in .qgs project files (FR and EN) to the DDR repository. \
    It can only republish vector layers but the layers can be stored in any format supported by QGIS (e.g. GPKG, \
    SHP, PostGIS, ...).  The style, service information, metadata stored in the .qgs project can be updated. \
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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
#        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def update_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = DdrInfo.get_http_environment()
        url += "/api/update"
        #url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        Utils.push_info(feedback, f"INFO: Updating to DDR")
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


class DdrValidate(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrValidate()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'validate'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Validate Project')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This processing plugin validates the content of a QGIS project files (.qgs) FR and EN. If the validation \
    pass, the project can be publish, republish or unpublish to the DDR repository. If the validation fail, \
    you must edit the QGIS  and rerun the validation. This plugin does not write anything into the QGIS \
    server so you can rerun it safely until there is no error and than run the appropriate tool (publish, \
    unpublish or republish). """

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
        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def validate_project_file(ctl_file, parameters, context, feedback):
        """"""

#        import web_pdb; web_pdb.set_trace()
        url = DdrInfo.get_http_environment()
        url += "/api/validate"
        #url = 'https://qgis.ddr-stage.services.geo.ca/api/validate'
        headers = {'accept': 'application/json',
                   'charset': 'utf-8',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)
                   }
        data = {
            'operation': ctl_file.validation_type.lower()
        }
        files = {
            'zip_file': open(ctl_file.zip_file_name, 'rb')
        }

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


class DdrUnpublish(QgsProcessingAlgorithm):
    """Main class defining the Unpublish algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrUnpublish()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'unpublish'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Unpublish Project')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management (second step)'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin removes the content of a QGIS project file (.qgs) stored to the DDR repository.
        
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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def unpublish_project_file(ctl_file, parameters, context, feedback):
        """Unpublish a QGIS project file """

        url = DdrInfo.get_http_environment()
        url += "/api/unpublish"
        #url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LoginToken.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}
        Utils.push_info(feedback, f"INFO: Publishing to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Delete Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file to publish: {ctl_file.zip_file_name}")

        try:
            response = requests.delete(url, files=files, verify=False, headers=headers)
            ResponseCodes.unpublish_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """
        try:
            dispatch_algorithm(self, "UNPUBLISH", parameters, context, feedback)
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
        return 'Authentication (first step)'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin logs into the DDR repository server. The authentication operation is \
        mandatory before  doing any management operation: publication, unpublication republication, or validation. 
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
        Utils.push_info(feedback, f"INFO: Execution environment: {environment}")
        DdrInfo.add_environment(environment)


#        authMgr = QgsApplication.authManager()
#        if authMgr.authenticationDatabasePath():
#            # already initialized => we are inside a QGIS app.
#            if authMgr.masterPasswordIsSet():
#                msg = 'Authentication master password not recognized'
#                assert authMgr.masterPasswordSame("MasterPass123$"), msg
#            else:
#                msg = 'Master password could not be set'
#                # The verify parameter checks if the hash of the password was
#                # already saved in the authentication db
#                assert authMgr.setMasterPassword("MasterPass123$", verify=True), msg
#        else:
#            # outside qgis, e.g. in a testing environment => setup env var before
#            # db init
#            os.environ['QGIS_AUTH_DB_DIR_PATH'] = "/path/where/located/qgis-auth.db"
#            msg = 'Master password could not be set'
#            assert authMgr.setMasterPassword("your master password", True), msg
#            authMgr.init("/path/where/located/qgis-auth.db")

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

        return username, password

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            # Create the control file data structure
            ctl_file = ControlFile()
            (username, password) = self.read_parameters(ctl_file, parameters, context, feedback)

            Utils.create_access_token(username, password, ctl_file, feedback)

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
