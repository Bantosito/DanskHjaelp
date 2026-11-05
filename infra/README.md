# Infrastructure

Three Terraform stacks with separate state, so a bad app change can't touch the database server.

| Stack | Holds | Applied by |
|---|---|---|
| `bootstrap` | State storage, GitHub sign-in identities, resource groups, budget | Me, locally, rarely |
| `shared` | Network, Postgres, registry, logs, Container Apps environment | Pipeline |
| `app` | One environment's app, jobs and Key Vault | Pipeline, once per environment |

## Bootstrap

The pipeline can't create the identities it signs in with, so this stack is applied by hand.

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export TF_VAR_budget_email=$(az account show --query user.name -o tsv)

# Once per subscription: the pipeline identities aren't allowed to do this.
for provider in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry \
  Microsoft.DBforPostgreSQL Microsoft.KeyVault Microsoft.Network Microsoft.ManagedIdentity \
  Microsoft.Storage Microsoft.Consumption; do
  az provider register --namespace "$provider"
done

cd infra/bootstrap
terraform init -backend-config=../backend.hcl
terraform apply
```
