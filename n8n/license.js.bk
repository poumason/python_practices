"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.License = void 0;
const config_1 = require("@n8n/config");
const di_1 = require("@n8n/di");
const license_sdk_1 = require("@n8n_io/license-sdk");
const n8n_core_1 = require("n8n-core");
const config_2 = __importDefault(require("./config"));
const settings_repository_1 = require("./databases/repositories/settings.repository");
const on_shutdown_1 = require("./decorators/on-shutdown");
const license_metrics_service_1 = require("./metrics/license-metrics.service");
const constants_1 = require("./constants");
const LICENSE_RENEWAL_DISABLED_WARNING = 'Automatic license renewal is disabled. The license will not renew automatically, and access to licensed features may be lost!';
let License = class License {
    constructor(logger, instanceSettings, settingsRepository, licenseMetricsService, globalConfig) {
        this.logger = logger;
        this.instanceSettings = instanceSettings;
        this.settingsRepository = settingsRepository;
        this.licenseMetricsService = licenseMetricsService;
        this.globalConfig = globalConfig;
        this.isShuttingDown = false;
        this.logger = this.logger.scoped('license');
    }
    async init(forceRecreate = false) {
        if (this.manager && !forceRecreate) {
            this.logger.warn('License manager already initialized or shutting down');
            return;
        }
        if (this.isShuttingDown) {
            this.logger.warn('License manager already shutting down');
            return;
        }
        const { instanceType } = this.instanceSettings;
        const isMainInstance = instanceType === 'main';
        const server = this.globalConfig.license.serverUrl;
        const offlineMode = !isMainInstance;
        const autoRenewOffset = this.globalConfig.license.autoRenewOffset;
        const saveCertStr = isMainInstance
            ? async (value) => await this.saveCertStr(value)
            : async () => { };
        const onFeatureChange = isMainInstance
            ? async (features) => await this.onFeatureChange(features)
            : async () => { };
        const collectUsageMetrics = isMainInstance
            ? async () => await this.licenseMetricsService.collectUsageMetrics()
            : async () => [];
        const collectPassthroughData = isMainInstance
            ? async () => await this.licenseMetricsService.collectPassthroughData()
            : async () => ({});
        const { isLeader } = this.instanceSettings;
        const { autoRenewalEnabled } = this.globalConfig.license;
        const shouldRenew = isLeader && autoRenewalEnabled;
        if (isLeader && !autoRenewalEnabled)
            this.logger.warn(LICENSE_RENEWAL_DISABLED_WARNING);
        try {
            this.manager = new license_sdk_1.LicenseManager({
                server,
                tenantId: this.globalConfig.license.tenantId,
                productIdentifier: `n8n-${constants_1.N8N_VERSION}`,
                autoRenewEnabled: shouldRenew,
                renewOnInit: shouldRenew,
                autoRenewOffset,
                offlineMode,
                logger: this.logger,
                loadCertStr: async () => await this.loadCertStr(),
                saveCertStr,
                deviceFingerprint: () => this.instanceSettings.instanceId,
                collectUsageMetrics,
                collectPassthroughData,
                onFeatureChange,
            });
            await this.manager.initialize();
            this.logger.debug('License initialized');
        }
        catch (error) {
            if (error instanceof Error) {
                this.logger.error('Could not initialize license manager sdk', { error });
            }
        }
    }
    async loadCertStr() {
        const ephemeralLicense = this.globalConfig.license.cert;
        if (ephemeralLicense) {
            return ephemeralLicense;
        }
        const databaseSettings = await this.settingsRepository.findOne({
            where: {
                key: constants_1.SETTINGS_LICENSE_CERT_KEY,
            },
        });
        return databaseSettings?.value ?? '';
    }
    async onFeatureChange(_features) {
        this.logger.debug('License feature change detected', _features);
        if (config_2.default.getEnv('executions.mode') === 'queue' && this.globalConfig.multiMainSetup.enabled) {
            const isMultiMainLicensed = _features[constants_1.LICENSE_FEATURES.MULTIPLE_MAIN_INSTANCES] ?? false;
            this.instanceSettings.setMultiMainLicensed(isMultiMainLicensed);
            if (this.instanceSettings.isMultiMain && !this.instanceSettings.isLeader) {
                this.logger
                    .scoped(['scaling', 'multi-main-setup', 'license'])
                    .debug('Instance is not leader, skipping sending of "reload-license" command...');
                return;
            }
            if (this.globalConfig.multiMainSetup.enabled && !isMultiMainLicensed) {
                this.logger
                    .scoped(['scaling', 'multi-main-setup', 'license'])
                    .debug('License changed with no support for multi-main setup - no new followers will be allowed to init. To restore multi-main setup, please upgrade to a license that supports this feature.');
            }
        }
        if (config_2.default.getEnv('executions.mode') === 'queue') {
            const { Publisher } = await Promise.resolve().then(() => __importStar(require('./scaling/pubsub/publisher.service')));
            await di_1.Container.get(Publisher).publishCommand({ command: 'reload-license' });
        }
        const isS3Selected = config_2.default.getEnv('binaryDataManager.mode') === 's3';
        const isS3Available = config_2.default.getEnv('binaryDataManager.availableModes').includes('s3');
        const isS3Licensed = _features['feat:binaryDataS3'];
        if (isS3Selected && isS3Available && !isS3Licensed) {
            this.logger.debug('License changed with no support for external storage - blocking writes on object store. To restore writes, please upgrade to a license that supports this feature.');
            di_1.Container.get(n8n_core_1.ObjectStoreService).setReadonly(true);
        }
    }
    async saveCertStr(value) {
        if (this.globalConfig.license.cert)
            return;
        await this.settingsRepository.upsert({
            key: constants_1.SETTINGS_LICENSE_CERT_KEY,
            value,
            loadOnStartup: false,
        }, ['key']);
    }
    async activate(activationKey) {
        if (!this.manager) {
            return;
        }
        await this.manager.activate(activationKey);
        this.logger.debug('License activated');
    }
    async reload() {
        if (!this.manager) {
            return;
        }
        await this.manager.reload();
        this.logger.debug('License reloaded');
    }
    async renew() {
        if (!this.manager) {
            return;
        }
        await this.manager.renew();
        this.logger.debug('License renewed');
    }
    async shutdown() {
        this.isShuttingDown = true;
        if (!this.manager) {
            return;
        }
        await this.manager.shutdown();
        this.logger.debug('License shut down');
    }
    isFeatureEnabled(feature) {
        return this.manager?.hasFeatureEnabled(feature) ?? false;
    }
    isSharingEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.SHARING);
    }
    isLogStreamingEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.LOG_STREAMING);
    }
    isLdapEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.LDAP);
    }
    isSamlEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.SAML);
    }
    isAiAssistantEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.AI_ASSISTANT);
    }
    isAskAiEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.ASK_AI);
    }
    isAiCreditsEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.AI_CREDITS);
    }
    isAdvancedExecutionFiltersEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.ADVANCED_EXECUTION_FILTERS);
    }
    isAdvancedPermissionsLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.ADVANCED_PERMISSIONS);
    }
    isDebugInEditorLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.DEBUG_IN_EDITOR);
    }
    isBinaryDataS3Licensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.BINARY_DATA_S3);
    }
    isMultiMainLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.MULTIPLE_MAIN_INSTANCES);
    }
    isVariablesEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.VARIABLES);
    }
    isSourceControlLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.SOURCE_CONTROL);
    }
    isExternalSecretsEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.EXTERNAL_SECRETS);
    }
    isWorkflowHistoryLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.WORKFLOW_HISTORY);
    }
    isAPIDisabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.API_DISABLED);
    }
    isWorkerViewLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.WORKER_VIEW);
    }
    isProjectRoleAdminLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.PROJECT_ROLE_ADMIN);
    }
    isProjectRoleEditorLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.PROJECT_ROLE_EDITOR);
    }
    isProjectRoleViewerLicensed() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.PROJECT_ROLE_VIEWER);
    }
    isCustomNpmRegistryEnabled() {
        return this.isFeatureEnabled(constants_1.LICENSE_FEATURES.COMMUNITY_NODES_CUSTOM_REGISTRY);
    }
    getCurrentEntitlements() {
        return this.manager?.getCurrentEntitlements() ?? [];
    }
    getFeatureValue(feature) {
        return this.manager?.getFeatureValue(feature);
    }
    getManagementJwt() {
        if (!this.manager) {
            return '';
        }
        return this.manager.getManagementJwt();
    }
    getMainPlan() {
        if (!this.manager) {
            return undefined;
        }
        const entitlements = this.getCurrentEntitlements();
        if (!entitlements.length) {
            return undefined;
        }
        return entitlements.find((entitlement) => entitlement.productMetadata?.terms?.isMainPlan);
    }
    getConsumerId() {
        return this.manager?.getConsumerId() ?? 'unknown';
    }
    getUsersLimit() {
        return this.getFeatureValue(constants_1.LICENSE_QUOTAS.USERS_LIMIT) ?? constants_1.UNLIMITED_LICENSE_QUOTA;
    }
    getTriggerLimit() {
        return this.getFeatureValue(constants_1.LICENSE_QUOTAS.TRIGGER_LIMIT) ?? constants_1.UNLIMITED_LICENSE_QUOTA;
    }
    getVariablesLimit() {
        return this.getFeatureValue(constants_1.LICENSE_QUOTAS.VARIABLES_LIMIT) ?? constants_1.UNLIMITED_LICENSE_QUOTA;
    }
    getAiCredits() {
        return this.getFeatureValue(constants_1.LICENSE_QUOTAS.AI_CREDITS) ?? 0;
    }
    getWorkflowHistoryPruneLimit() {
        return (this.getFeatureValue(constants_1.LICENSE_QUOTAS.WORKFLOW_HISTORY_PRUNE_LIMIT) ?? constants_1.UNLIMITED_LICENSE_QUOTA);
    }
    getTeamProjectLimit() {
        return this.getFeatureValue(constants_1.LICENSE_QUOTAS.TEAM_PROJECT_LIMIT) ?? 0;
    }
    getPlanName() {
        return this.getFeatureValue('planName') ?? 'Community';
    }
    getInfo() {
        if (!this.manager) {
            return 'n/a';
        }
        return this.manager.toString();
    }
    isWithinUsersLimit() {
        return this.getUsersLimit() === constants_1.UNLIMITED_LICENSE_QUOTA;
    }
    async reinit() {
        this.manager?.reset();
        await this.init(true);
        this.logger.debug('License reinitialized');
    }
};
exports.License = License;
__decorate([
    (0, on_shutdown_1.OnShutdown)(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", []),
    __metadata("design:returntype", Promise)
], License.prototype, "shutdown", null);
exports.License = License = __decorate([
    (0, di_1.Service)(),
    __metadata("design:paramtypes", [n8n_core_1.Logger,
        n8n_core_1.InstanceSettings,
        settings_repository_1.SettingsRepository,
        license_metrics_service_1.LicenseMetricsService,
        config_1.GlobalConfig])
], License);
//# sourceMappingURL=license.js.map