param(
    [ValidateSet('install', 'update', 'uninstall', 'rollback')]
    [string]$Action = 'install',
    [string]$HomeRoot = $HOME
)

$Installer = Join-Path $PSScriptRoot 'install.py'
python $Installer $Action --home $HomeRoot
exit $LASTEXITCODE
