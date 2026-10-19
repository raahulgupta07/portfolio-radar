// Portfolio Radar on Azure: Container Apps (gateway, worker, web), PostgreSQL Flexible Server,
// Key Vault, Container Registry and one managed identity per part. See docs/deploy-azure.md.
//
//   az deployment group create -g rg-portfolio-radar -f infra/main.bicep -p infra/main.bicepparam
//
// First run with deployApps=false (creates the registry), push the images, then run again with
// deployApps=true. The GitHub Actions workflow .github/workflows/deploy.yml does both.

targetScope = 'resourceGroup'

@description('Short name used in every resource name, e.g. radar')
@minLength(3)
@maxLength(12)
param prefix string = 'radar'

param location string = resourceGroup().location

@description('false on the first run: create the registry and data services only')
param deployApps bool = true

@description('Image tag to run: the git commit SHA (CI sets it; no "latest")')
@minLength(7)
param imageTag string

@description('PostgreSQL admin password. Stored in Key Vault as part of database-url; never in app settings.')
@secure()
param postgresAdminPassword string

// City SSO (Microsoft Entra ID)
@description('Entra tenant ID')
param entraTenantId string

@description('Gateway API app registration: the audience it checks (its client ID for v2 tokens, or its App ID URI for v1)')
param gatewayAudience string

@description('Scope the web app and the worker ask for, e.g. api://city-mcp-gateway/.default')
param gatewayScope string

@description('Entra group object ID → roles, e.g. {"<guid>": ["viewer","admin"]}. Admin → Connections can change it later.')
param entraGroupRoles object = {}

@description('Web app registration (sign-in) client ID')
param webClientId string

@description('Web app registration client secret. Stored in Key Vault.')
@secure()
param webClientSecret string

@description('Scope the web app asks for on behalf of the user, e.g. api://city-mcp-gateway/access')
param webApiScope string

@description('Custom domain for the web app, e.g. https://portfolio.cityholdings.com.mm. Empty = the Container Apps address')
param webOrigin string = ''

@description('true = the gateway is reachable from outside the environment (City agents such as CityGPT via /omni). false = only the web app and worker reach it')
param gatewayExternal bool = false

@description('IP ranges allowed to reach the web app (CIDR). Empty = anyone; City SSO still guards every page.')
param webAllowedIps array = []

@description('Two-way Teams chat: the bot app registration client ID. Empty = no Azure Bot. Its secret is pasted in Admin → Connections → Teams')
param teamsBotAppId string = ''

param timezone string = 'Asia/Yangon'

param tags object = {
  app: 'portfolio-radar'
  owner: 'City Holdings IT'
}

var name = toLower(prefix)
var suffix = uniqueString(resourceGroup().id)
var kvName = take('kv-${name}-${suffix}', 24) // the app's own secrets: database URL, web client secret
var kvAppName = take('kva-${name}-${suffix}', 24) // secrets admins paste in Admin (tracker tokens, LLM key…)
var acrName = 'acr${replace(name, '-', '')}${suffix}'
var pgName = 'pg-${name}-${suffix}'
var gatewayAppName = 'ca-${name}-mcp'
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  kvSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  kvSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
}

// -- logs ---------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${name}-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 90
  }
}

// -- network: apps and database talk privately ------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${name}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.40.0.0/16'] }
    subnets: [
      {
        name: 'apps'
        properties: {
          addressPrefix: '10.40.0.0/23'
          delegations: [{ name: 'apps', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'db'
        properties: {
          addressPrefix: '10.40.2.0/24'
          delegations: [{ name: 'db', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }]
        }
      }
      {
        name: 'endpoints'
        properties: { addressPrefix: '10.40.3.0/24' }
      }
    ]
  }
}

resource pgDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: '${name}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource pgDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: pgDns
  name: 'vnet-${name}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

// -- database --------------------------------------------------------------------------

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: pgName
  location: location
  tags: tags
  sku: { name: 'Standard_B2s', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'radaradmin'
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32, autoGrow: 'Enabled' }
    backup: { backupRetentionDays: 14, geoRedundantBackup: 'Disabled' }
    network: {
      delegatedSubnetResourceId: vnet.properties.subnets[1].id
      privateDnsZoneArmResourceId: pgDns.id
      publicNetworkAccess: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
  }
  dependsOn: [pgDnsLink]
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: 'radar'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource pgTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: pg
  name: 'require_secure_transport'
  properties: { value: 'on', source: 'user-override' }
}

// -- secrets ---------------------------------------------------------------------------

// Two vaults. Admins can write any name in the app vault (through the gateway), so the app's own secrets
// live in a vault the gateway may only read one secret from. Both are reachable only from the VNet.
var vaultProps = {
  tenantId: subscription().tenantId
  sku: { family: 'A', name: 'standard' }
  enableRbacAuthorization: true
  enableSoftDelete: true
  softDeleteRetentionInDays: 90
  enablePurgeProtection: true
  publicNetworkAccess: 'Disabled'
  networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
}

resource kv 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: kvName
  location: location
  tags: tags
  properties: vaultProps
}

resource kvApp 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: kvAppName
  location: location
  tags: tags
  properties: vaultProps
}

resource kvDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource kvDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: kvDns
  name: 'vnet-${name}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

var vaults = [
  { name: kvName, id: kv.id }
  { name: kvAppName, id: kvApp.id }
]

resource kvEndpoints 'Microsoft.Network/privateEndpoints@2024-05-01' = [for v in vaults: {
  name: 'pe-${v.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet.properties.subnets[2].id }
    privateLinkServiceConnections: [{
      name: v.name
      properties: { privateLinkServiceId: v.id, groupIds: ['vault'] }
    }]
  }
}]

resource kvEndpointDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = [for (v, i) in vaults: {
  parent: kvEndpoints[i]
  name: 'vault'
  properties: {
    privateDnsZoneConfigs: [{ name: 'vault', properties: { privateDnsZoneId: kvDns.id } }]
  }
}]

resource kvDatabaseUrl 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg://radaradmin:${uriComponent(postgresAdminPassword)}@${pg.properties.fullyQualifiedDomainName}:5432/radar?sslmode=require'
    contentType: 'SQLAlchemy URL'
  }
}

resource kvWebSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'web-entra-client-secret'
  properties: { value: webClientSecret }
}

// -- container registry ---------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// -- identities: one per part, one per worker job ---------------------------------------------

var identityNames = ['gateway', 'worker', 'web', 'adapter', 'radar-job', 'radar', 'notifier']

resource ids 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = [for n in identityNames: {
  name: 'id-${name}-${n}'
  location: location
  tags: tags
}]

// ids[0] gateway, ids[1] worker, ids[2] web, ids[3..6] the worker's four jobs (gateway sign-in only)

resource pullRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in range(0, 3): {
  name: guid(acr.id, ids[i].id, roles.acrPull)
  scope: acr
  properties: {
    principalId: ids[i].properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}]

// The gateway saves secrets pasted in Admin (set_secret): write access to the app vault only.
resource kvGateway 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kvApp.id, ids[0].id, roles.kvSecretsOfficer)
  scope: kvApp
  properties: {
    principalId: ids[0].properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsOfficer)
  }
}

// The worker reads secrets pasted in Admin (LLM key, Teams webhook and bot secret, SMTP password).
resource kvWorkerApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kvApp.id, ids[1].id, roles.kvSecretsUser)
  scope: kvApp
  properties: {
    principalId: ids[1].properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
  }
}

// Each app reads only its own secret from the app's vault: gateway and worker the database URL, web its client secret.
resource kvDbReaders 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in range(0, 2): {
  name: guid(kvDatabaseUrl.id, ids[i].id, roles.kvSecretsUser)
  scope: kvDatabaseUrl
  properties: {
    principalId: ids[i].properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
  }
}]

resource kvWebReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kvWebSecret.id, ids[2].id, roles.kvSecretsUser)
  scope: kvWebSecret
  properties: {
    principalId: ids[2].properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
  }
}

// -- container apps ---------------------------------------------------------------------------

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${name}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: vnet.properties.subnets[0].id
      internal: false
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}

var image = '${acr.properties.loginServer}/portfolio-radar'
var gatewayInternalHost = '${gatewayAppName}.internal.${env.properties.defaultDomain}'
var gatewayPublicHost = '${gatewayAppName}.${env.properties.defaultDomain}'
var webHost = 'ca-${name}-web.${env.properties.defaultDomain}'
var origin = empty(webOrigin) ? 'https://${webHost}' : webOrigin
// The web app and worker reach the gateway over https: its internal address, or its public one if external.
var gatewayUrlInside = gatewayExternal ? 'https://${gatewayPublicHost}' : 'https://${gatewayInternalHost}'

// Service callers the gateway accepts, by managed identity client ID (see app/servicetokens.py).
var entraApps = {
  '${ids[3].properties.clientId}': { kind: 'service', id: 'adapter', roles: ['adapter'] }
  '${ids[4].properties.clientId}': { kind: 'service', id: 'radar-job', roles: ['radar'] }
  '${ids[5].properties.clientId}': { kind: 'agent', id: 'radar', roles: ['agent'] }
  '${ids[6].properties.clientId}': { kind: 'service', id: 'notifier', roles: ['notifier'] }
}

var common = [
  { name: 'APP_ENV', value: 'prod' }
  { name: 'TIMEZONE', value: timezone }
  { name: 'SECRET_STORE', value: 'keyvault' }
  { name: 'KEY_VAULT_URL', value: kvApp.properties.vaultUri }
]

resource gateway 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: gatewayAppName
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${ids[0].id}': {} } }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: gatewayExternal
        targetPort: 8000
        transport: 'http'
        allowInsecure: false // https only, also inside the environment (people's tokens travel here)
      }
      registries: [{ server: acr.properties.loginServer, identity: ids[0].id }]
      secrets: [{ name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: ids[0].id }]
    }
    template: {
      containers: [{
        name: 'mcp'
        image: '${image}-mcp:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: concat(common, [
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'AZURE_CLIENT_ID', value: ids[0].properties.clientId }
          { name: 'SOURCE_MODE', value: 'live' }
          { name: 'ENTRA_TENANT_ID', value: entraTenantId }
          { name: 'ENTRA_AUDIENCE', value: gatewayAudience }
          { name: 'ENTRA_GROUP_ROLES', value: string(entraGroupRoles) }
          { name: 'ENTRA_APPS', value: string(entraApps) }
          { name: 'ENTRA_USER_APPS', value: string([webClientId]) }
          { name: 'DEV_TOKENS', value: '{}' }
          { name: 'MCP_ALLOWED_HOSTS', value: string([gatewayAppName, '${gatewayAppName}:*', gatewayInternalHost, '${gatewayInternalHost}:*', gatewayPublicHost, '${gatewayPublicHost}:*']) }
          { name: 'MCP_ALLOWED_ORIGINS', value: string([origin]) }
        ])
        probes: [
          { type: 'Liveness', httpGet: { path: '/healthz', port: 8000 }, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/readyz', port: 8000 }, periodSeconds: 10, initialDelaySeconds: 10 }
        ]
      }]
      // One copy: it applies database migrations at start, and keeps rate limits in memory (docs/load-test.md).
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [pullRoles, kvGateway, kvDbReaders, kvEndpointDns]
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-${name}-worker'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${ids[1].id}': {}
      '${ids[3].id}': {}
      '${ids[4].id}': {}
      '${ids[5].id}': {}
      '${ids[6].id}': {}
    }
  }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: acr.properties.loginServer, identity: ids[1].id }]
      // The nightly adapter writes the synced data (docs/architecture.md: only the gateway and the adapter use the database).
      secrets: [{ name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: ids[1].id }]
    }
    template: {
      containers: [{
        name: 'worker'
        image: '${image}-mcp:${imageTag}'
        command: ['python', '-m', 'app.worker']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat(common, [
          { name: 'AZURE_CLIENT_ID', value: ids[1].properties.clientId }
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'GATEWAY_URL', value: gatewayUrlInside }
          { name: 'SERVICE_AUTH', value: 'managed_identity' }
          { name: 'GATEWAY_SCOPE', value: gatewayScope }
          { name: 'ADAPTER_CLIENT_ID', value: ids[3].properties.clientId }
          { name: 'RADAR_JOB_CLIENT_ID', value: ids[4].properties.clientId }
          { name: 'RADAR_AGENT_CLIENT_ID', value: ids[5].properties.clientId }
          { name: 'NOTIFIER_CLIENT_ID', value: ids[6].properties.clientId }
        ])
      }]
      // Exactly one copy: it holds the nightly schedule.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [pullRoles, kvWorkerApp, kvDbReaders, gateway]
}

resource web 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-${name}-web'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${ids[2].id}': {} } }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
        allowInsecure: false
        ipSecurityRestrictions: [for (cidr, i) in webAllowedIps: {
          name: 'allow-${i}'
          action: 'Allow'
          ipAddressRange: cidr
        }]
      }
      registries: [{ server: acr.properties.loginServer, identity: ids[2].id }]
      secrets: [{ name: 'entra-client-secret', keyVaultUrl: kvWebSecret.properties.secretUri, identity: ids[2].id }]
    }
    template: {
      containers: [{
        name: 'web'
        image: '${image}-web:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'GATEWAY_URL', value: gatewayUrlInside }
          { name: 'MCP_PUBLIC_URL', value: gatewayExternal ? 'https://${gatewayPublicHost}' : '' }
          { name: 'ORIGIN', value: origin }
          { name: 'ENTRA_TENANT_ID', value: entraTenantId }
          { name: 'ENTRA_CLIENT_ID', value: webClientId }
          { name: 'ENTRA_CLIENT_SECRET', secretRef: 'entra-client-secret' }
          { name: 'ENTRA_API_SCOPE', value: webApiScope }
          { name: 'DEV_LOGIN', value: 'false' }
          { name: 'MCP_CACHE_SECONDS', value: '60' }
        ]
        probes: [
          { type: 'Liveness', httpGet: { path: '/healthz', port: 3000 }, periodSeconds: 30 }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [pullRoles, kvWebReader, gateway]
}

// -- Teams chat (docs/teams-bot.md) ----------------------------------------------------------

resource bot 'Microsoft.BotService/botServices@2022-09-15' = if (deployApps && !empty(teamsBotAppId)) {
  name: 'bot-${name}-${suffix}'
  location: 'global'
  kind: 'azurebot'
  sku: { name: 'F0' }
  tags: tags
  properties: {
    displayName: 'Radar'
    description: 'Ask Radar about City Holdings projects'
    endpoint: '${origin}/api/teams/messages'
    msaAppId: teamsBotAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: entraTenantId
    disableLocalAuth: false
  }
}

resource botTeams 'Microsoft.BotService/botServices/channels@2022-09-15' = if (deployApps && !empty(teamsBotAppId)) {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: { isEnabled: true }
  }
}

// -- outputs ---------------------------------------------------------------------------------

output registry string = acr.properties.loginServer
output keyVaultUrl string = kvApp.properties.vaultUri
output webUrl string = origin
output webRedirectUri string = '${origin}/auth/callback'
output teamsMessagingEndpoint string = '${origin}/api/teams/messages'
output gatewayUrl string = gatewayExternal ? 'https://${gatewayPublicHost}' : 'https://${gatewayInternalHost} (inside the environment only)'
@description('Give these managed identities access to the gateway API in Entra (they sign in as the worker jobs)')
output workerJobIdentities object = {
  adapter: ids[3].properties.clientId
  radarJob: ids[4].properties.clientId
  radar: ids[5].properties.clientId
  notifier: ids[6].properties.clientId
}
