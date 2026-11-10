// =============================================================================
// UNDEPLOYED FUTURE OPTION — NOT FOR THIS SUBSCRIPTION
// =============================================================================
// Production data plane for ~200k resumes / month.
// Do not run `az deployment` here: pay-as-you-go with spending limit Off.
// See README.md and docs/production-infra-200k.md.
// =============================================================================
targetScope = 'resourceGroup'

@description('Primary region for storage, bus, ACR, Key Vault, Search.')
param location string = resourceGroup().location

@description('Postgres region (may differ when Flexible Server capacity is constrained).')
param postgresLocation string = 'westus2'

@description('Suffix for globally unique names.')
param nameSuffix string

@description('Admin login for Flexible Server.')
param postgresAdminLogin string = 'meridianadmin'

@secure()
param postgresAdminPassword string

@description('Postgres General Purpose SKU name (Ddsv5 family).')
@allowed(['Standard_D2ds_v5', 'Standard_D4ds_v5', 'Standard_D8ds_v5'])
param postgresSkuName string = 'Standard_D4ds_v5'

@description('Postgres storage GB (minimum 32).')
@minValue(32)
param postgresStorageGb int = 32

@description('AI Search Basic service name (lowercase, globally unique).')
param searchServiceName string

var postgresName = 'meridian-pg-prod-${nameSuffix}'
var storageName = take('meridianstprod${replace(nameSuffix, '-', '')}', 24)
var serviceBusName = 'meridian-sb-prod-${nameSuffix}'
var acrName = take('macprod${replace(nameSuffix, '-', '')}', 50)
var keyVaultName = take('meridiankvprod${replace(nameSuffix, '-', '')}', 24)

var commonTags = {
  project: 'recruitment-intelligence'
  cost: 'production-200k-undeployed'
  purpose: 'not-for-this-subscription'
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: postgresLocation
  sku: {
    name: postgresSkuName
    tier: 'GeneralPurpose'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageGb
    }
    backup: {
      backupRetentionDays: 14
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
  tags: union(commonTags, { sku: postgresSkuName })
}

resource postgresFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'recruitment'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
  tags: union(commonTags, { sku: 'Standard_LRS' })
}

resource resumesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/resumes'
  properties: {
    publicAccess: 'None'
  }
}

resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/exports'
  properties: {
    publicAccess: 'None'
  }
}

resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: serviceBusName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  tags: union(commonTags, { sku: 'Standard' })
}

resource queueIngestion 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'resume-ingestion'
  properties: {
    maxDeliveryCount: 10
  }
}

resource queueEvaluation 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'evaluation-runs'
  properties: {
    maxDeliveryCount: 10
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
  tags: union(commonTags, { sku: 'Basic' })
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
  tags: union(commonTags, { sku: 'standard' })
}

// Free tier cannot hold 200k documents. Basic is the production floor for this volume.
resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 2
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
  tags: union(commonTags, { sku: 'basic' })
}

output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output storageAccountName string = storage.name
output serviceBusNamespace string = serviceBus.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultUri string = keyVault.properties.vaultUri
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchSku string = search.sku.name
output undeployedWarning string = 'This template is a production blueprint only. Do not deploy on the free-tier-locked subscription.'
