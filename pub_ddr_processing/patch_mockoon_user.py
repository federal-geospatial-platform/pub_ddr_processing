0/0
from qgis.core import  QgsAuthMethodConfig, QgsApplication
cfg = QgsAuthMethodConfig()
cfg.setMethod("Basic")
cfg.setName("mfrthn8")
cfg.setConfig("username", "pil123456")
cfg.setConfig("password", "a123456")
cfg.setId("p7h9tdd")
auth_manager = QgsApplication.authManager()
auth_manager.storeAuthenticationConfig(cfg)
cfg.id()
