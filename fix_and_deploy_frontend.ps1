# filepath: fix_and_deploy_frontend.ps1
# Script to fix frontend build issues and deploy to Azure Container Apps

Write-Host "Starting automated fix and deploy for frontend..."

# Step 1: Create .env.production from template
Write-Host "Creating .env.production..."
Copy-Item -Path "frontend\.env.production.template" -Destination "frontend\.env.production" -Force

# Step 1.5: Update package-lock.json
Write-Host "Updating package-lock.json..."
Push-Location frontend
npm install
Pop-Location

# Step 2: Add modified files and commit locally before pull
Write-Host "Staging local changes..."
git add frontend/package.json frontend/package-lock.json
git commit -m "Fix rollup-plugin-visualizer version to 5.12.0 and update lock file"

# Step 3: Git pull to sync with remote
Write-Host "Pulling latest changes from GitHub..."
try {
    git pull origin main --rebase
} catch {
    Write-Host "Error during git pull. Please resolve conflicts manually and re-run the script."
    exit 1
}

# Step 4: Add, commit, and push remaining changes
Write-Host "Committing and pushing changes..."
git add frontend/Dockerfile.prod
git commit -m "Fix frontend build: install dev deps and use npx tsc"
git push origin main

# Step 5: Build image in ACR
Write-Host "Building image in ACR..."
az acr build -g newsites -r axialacr12389 -t axial-frontend:latest -f Dockerfile.prod "https://github.com/OsvaldoVegaOses/app-jupter.git#main:frontend"

# Check if build succeeded (basic check)
if ($LASTEXITCODE -ne 0) {
    Write-Host "ACR build failed. Check logs above."
    exit 1
}

# Step 6: Create/update Container App
Write-Host "Creating Container App for frontend..."
$acrPassword = $env:ACR_PASSWORD
if ([string]::IsNullOrWhiteSpace($acrPassword)) {
    Write-Host "Missing ACR_PASSWORD. Export it as an environment variable before running this script."
    Write-Host "Example: `$env:ACR_PASSWORD = '<your-acr-password>'"
    exit 1
}

az containerapp create -g newsites -n axial-frontend --image axialacr12389.azurecr.io/axial-frontend:latest --environment axial-env --target-port 80 --ingress external --registry-server axialacr12389.azurecr.io --registry-username axialacr12389 --registry-password $acrPassword

Write-Host "Deployment complete! Frontend should be available at the URL shown above."
