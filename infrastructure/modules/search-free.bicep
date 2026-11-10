@description('Azure AI Search free tier only. Always free: 50 MB, 10,000 documents, 3 indexes, one service per subscription.')
@minLength(2)
@maxLength(60)
param name string

param location string

@description('Must remain free. Do not change to a paid SKU on this subscription.')
@allowed(['free'])
param skuName string = 'free'

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  sku: {
    name: skuName
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
  tags: {
    project: 'recruitment-intelligence'
    cost: 'always-free'
    sku: 'free'
  }
}

output id string = search.id
output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'
output sku string = search.sku.name
