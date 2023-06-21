from qgis.core import  QgsAuthMethodConfig, QgsApplication

authMgr = QgsApplication.authManager()
if authMgr.authenticationDatabasePath():
    # already initialized => we are inside a QGIS app.
    if authMgr.masterPasswordIsSet():
        msg = 'Authentication master password not recognized'
        assert authMgr.masterPasswordSame("MasterPass123$"), msg
    else:
        msg = 'Master password could not be set'
        # The verify parameter checks if the hash of the password was
        # already saved in the authentication db
        assert authMgr.setMasterPassword("MasterPass123$", verify=True), msg
else:
    # outside qgis, e.g. in a testing environment => setup env var before
    # db init
    os.environ['QGIS_AUTH_DB_DIR_PATH'] = "/path/where/located/qgis-auth.db"
    msg = 'Master password could not be set'
    assert authMgr.setMasterPassword("your master password", True), msg
    authMgr.init("/path/where/located/qgis-auth.db")

cfg = QgsAuthMethodConfig()
cfg.setMethod("Basic")
cfg.setName("mergin4")
cfg.setConfig("username", "pil123456")
cfg.setConfig("password", "a123456")
cfg.setId("p3m9sdd")
auth_manager = QgsApplication.authManager()
auth_manager.storeAuthenticationConfig(cfg, True)
cfg.id()