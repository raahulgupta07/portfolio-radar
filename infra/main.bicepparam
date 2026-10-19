// Values for infra/main.bicep. Secrets and per-run values come from environment variables
// (set by .github/workflows/deploy.yml from GitHub secrets and variables), never from this file.
using 'main.bicep'

param prefix = 'radar'
param location = 'southeastasia'
param deployApps = bool(readEnvironmentVariable('DEPLOY_APPS', 'true'))
param imageTag = readEnvironmentVariable('IMAGE_TAG')
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD')

// City SSO: fill in from the Entra app registrations (docs/deploy-azure.md, step 1)
param entraTenantId = readEnvironmentVariable('ENTRA_TENANT_ID')
param gatewayAudience = readEnvironmentVariable('GATEWAY_AUDIENCE')
param gatewayScope = readEnvironmentVariable('GATEWAY_SCOPE')
param webClientId = readEnvironmentVariable('WEB_CLIENT_ID')
param webClientSecret = readEnvironmentVariable('WEB_CLIENT_SECRET')
param webApiScope = readEnvironmentVariable('WEB_API_SCOPE')
param webOrigin = readEnvironmentVariable('WEB_ORIGIN', '')
param teamsBotAppId = readEnvironmentVariable('TEAMS_BOT_APP_ID', '')

// Admin → Connections → Sign-in can change group roles later without a deployment.
param entraGroupRoles = {}
param gatewayExternal = false
param webAllowedIps = []
