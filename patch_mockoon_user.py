0/0
from qgis.core import  QgsAuthMethodConfig, QgsApplication
cfg = QgsAuthMethodConfig()
cfg.setMethod("Basic")
cfg.setName("mergin4")
cfg.setConfig("username", "pil123456")
cfg.setConfig("password", "a123456")
cfg.setId("p3m9sdd")
auth_manager = QgsApplication.authManager()
auth_manager.storeAuthenticationConfig(cfg)
cfg.id()
