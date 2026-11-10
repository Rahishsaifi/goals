// Free-tier Azure footprint for Meridian / recruitment-intelligence.
// Paid resources are intentionally absent from this template.
targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Globally unique search service name (lowercase letters, digits, dashes).')
param searchServiceName string

@description('Hard lock: only the always-free Search SKU may be deployed from this template.')
@allowed(['free'])
param searchSku string = 'free'

module searchFree 'modules/search-free.bicep' = {
  name: 'search-free'
  params: {
    name: searchServiceName
    location: location
    skuName: searchSku
  }
}

output searchServiceName string = searchFree.outputs.name
output searchEndpoint string = searchFree.outputs.endpoint
output searchSkuDeployed string = searchFree.outputs.sku
output note string = 'Local Docker Compose still hosts PostgreSQL, blobs (Azurite), API, worker, and the web app. No paid Azure compute or database is defined here.'
