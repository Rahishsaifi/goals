// Temporary 10-day paid POC stack. Authorized by the operator after cost review.
// SKUs: Postgres B1ms, Storage Standard_LRS, Service Bus Standard, ACR Basic, Key Vault standard.
// NOT included: Container Apps, Foundry model deployments.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
@description('East US currently restricts new Flexible Server capacity; West US 2 is used for Postgres.')
param postgresLocation string = 'westus2'
param nameSuffix string
param clientIp string
param postgresAdminLogin string = 'meridianadmin'
@secure()
param postgresAdminPassword string

var postgresName = 'meridian-pg-${nameSuffix}'
var storageName = take('meridianst${replace(nameSuffix, '-', '')}', 24)
var serviceBusName = 'meridian-sb-${nameSuffix}'
var acrName = take('mac${replace(nameSuffix, '-', '')}', 50)
var keyVaultName = take('meridiankv${replace(nameSuffix, '-', '')}', 24)

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: postgresLocation
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
  tags: {
    project: 'recruitment-intelligence'
    cost: 'paid-poc-10d'
    sku: 'Standard_B1ms'
  }
}

resource postgresFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresFirewallClient 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowClientIp'
  properties: {
    startIpAddress: clientIp
    endIpAddress: clientIp
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
  tags: {
    project: 'recruitment-intelligence'
    cost: 'paid-poc-10d'
    sku: 'Standard_LRS'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource resumesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'resumes'
  properties: {
    publicAccess: 'None'
  }
}

resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'exports'
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
  tags: {
    project: 'recruitment-intelligence'
    cost: 'paid-poc-10d'
    sku: 'Standard'
  }
}

resource ingestionQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'resume-ingestion'
  properties: {
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 10
  }
}

resource evaluationQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'evaluation-runs'
  properties: {
    deadLetteringOnMessageExpiration: true
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
  tags: {
    project: 'recruitment-intelligence'
    cost: 'paid-poc-10d'
    sku: 'Basic'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    accessPolicies: []
  }
  tags: {
    project: 'recruitment-intelligence'
    cost: 'paid-poc-10d'
    sku: 'standard'
  }
}

output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output postgresName string = postgres.name
output postgresDatabase string = postgresDb.name
output postgresAdminLogin string = postgresAdminLogin
output storageAccountName string = storage.name
output serviceBusNamespace string = serviceBus.name
output serviceBusIngestionQueue string = ingestionQueue.name
output serviceBusEvaluationQueue string = evaluationQueue.name
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
