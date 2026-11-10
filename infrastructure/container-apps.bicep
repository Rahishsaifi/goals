// Operator-authorized deploy. Container Apps Consumption only.
// No Log Analytics workspace. Apps: 0.25 vCPU / 0.5 Gi.

@description('ACR login server, e.g. mac2610100151.azurecr.io')
param acrLoginServer string

@description('ACR admin username')
param acrUsername string

@secure()
param acrPassword string

@description('Image tag to deploy')
param imageTag string = 'poc'

@secure()
param databaseUrl string

@secure()
param storageConnectionString string

@secure()
param azureOpenAiEndpoint string = ''

@secure()
param azureOpenAiApiKey string = ''

param azureOpenAiDeployment string = 'gpt-4.1-mini'
param azureOpenAiApiVersion string = '2024-12-01-preview'
param modelProvider string = 'mock'
@secure()
param azureTranslatorEndpoint string = ''
@secure()
param azureTranslatorKey string = ''
param azureTranslatorRegion string = ''
param location string = resourceGroup().location

var envName = 'meridian-cae-poc'
var apiImage = '${acrLoginServer}/recruitment-api:${imageTag}'
var workerImage = '${acrLoginServer}/recruitment-worker:${imageTag}'
var webImage = '${acrLoginServer}/recruitment-web:${imageTag}'

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {}
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'meridian-api'
  location: location
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: true
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'database-url'
          value: databaseUrl
        }
        {
          name: 'storage-connection'
          value: storageConnectionString
        }
        {
          name: 'azure-openai-endpoint'
          value: azureOpenAiEndpoint
        }
        {
          name: 'azure-openai-api-key'
          value: azureOpenAiApiKey
        }
        {
          name: 'azure-translator-endpoint'
          value: azureTranslatorEndpoint
        }
        {
          name: 'azure-translator-key'
          value: azureTranslatorKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'APP_ENV', value: 'poc' }
            { name: 'MODEL_PROVIDER', value: modelProvider }
            { name: 'COOKIE_SECURE', value: 'true' }
            { name: 'COOKIE_SAMESITE', value: 'lax' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection' }
            { name: 'AZURE_STORAGE_CONTAINER_RESUMES', value: 'resumes' }
            { name: 'AZURE_STORAGE_CONTAINER_EXPORTS', value: 'exports' }
            { name: 'AZURE_OPENAI_ENDPOINT', secretRef: 'azure-openai-endpoint' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_TRANSLATOR_ENDPOINT', secretRef: 'azure-translator-endpoint' }
            { name: 'AZURE_TRANSLATOR_KEY', secretRef: 'azure-translator-key' }
            { name: 'AZURE_TRANSLATOR_REGION', value: azureTranslatorRegion }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'meridian-worker'
  location: location
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'database-url'
          value: databaseUrl
        }
        {
          name: 'storage-connection'
          value: storageConnectionString
        }
        {
          name: 'azure-openai-endpoint'
          value: azureOpenAiEndpoint
        }
        {
          name: 'azure-openai-api-key'
          value: azureOpenAiApiKey
        }
        {
          name: 'azure-translator-endpoint'
          value: azureTranslatorEndpoint
        }
        {
          name: 'azure-translator-key'
          value: azureTranslatorKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: workerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'APP_ENV', value: 'poc' }
            { name: 'MODEL_PROVIDER', value: modelProvider }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection' }
            { name: 'AZURE_STORAGE_CONTAINER_RESUMES', value: 'resumes' }
            { name: 'AZURE_STORAGE_CONTAINER_EXPORTS', value: 'exports' }
            { name: 'AZURE_OPENAI_ENDPOINT', secretRef: 'azure-openai-endpoint' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_TRANSLATOR_ENDPOINT', secretRef: 'azure-translator-endpoint' }
            { name: 'AZURE_TRANSLATOR_KEY', secretRef: 'azure-translator-key' }
            { name: 'AZURE_TRANSLATOR_REGION', value: azureTranslatorRegion }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'meridian-web'
  location: location
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'API_UPSTREAM_URL', value: 'http://meridian-api' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    apiApp
  ]
}

output webFqdn string = webApp.properties.configuration.ingress.fqdn
output apiFqdn string = apiApp.properties.configuration.ingress.fqdn
output environmentId string = managedEnv.id
