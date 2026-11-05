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

## How the other stacks are applied

`shared` and `app` are only applied by `.github/workflows/deploy.yml`. Every PR that touches `infra/` gets a plan posted as a comment, so changes are visible before they happen.

The first deploy creates Key Vault with placeholder values for the Telegram token and my Telegram ID. They are set by hand, so they never pass through this repo or Terraform state.

`infra/.trivyignore` lists the accepted security findings, each with its reason.
