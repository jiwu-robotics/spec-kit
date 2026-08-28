#!/usr/bin/env pwsh
# Setup implementation plan for a feature

[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$PathsOnly,
    [switch]$Help,
    # Capture extra positional arguments to match Bash/Python behavior.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'

# Show help if requested
if ($Help) {
    Write-Output "Usage: ./setup-plan.ps1 [-Json] [-PathsOnly] [-Help]"
    Write-Output "  -Json       Output results in JSON format"
    Write-Output "  -PathsOnly  Resolve paths without writing files"
    Write-Output "  -Help       Show this help message"
    exit 0
}

if ($RemainingArgs.Count -gt 0) {
    [Console]::Error.WriteLine("ERROR: Unknown option '$($RemainingArgs[0])'")
    exit 1
}

# Load common functions
. "$PSScriptRoot/common.ps1"

# Get all paths and variables from common functions.
# -PathsOnly must leave feature metadata, directories, and plan.md untouched.
if ($PathsOnly) {
    $paths = Get-FeaturePathsEnv -NoPersist -ReturnNullOnError
} else {
    $paths = Get-FeaturePathsEnv -ReturnNullOnError
}
if (-not $paths) {
    [Console]::Error.WriteLine("ERROR: Failed to resolve feature paths")
    exit 1
}

function Write-SetupPlanResult {
    param(
        [Parameter(Mandatory = $true)]$ResolvedPaths,
        [switch]$JsonMode
    )

    if ($JsonMode) {
        $result = [PSCustomObject]@{
            FEATURE_SPEC = $ResolvedPaths.FEATURE_SPEC
            IMPL_PLAN = $ResolvedPaths.IMPL_PLAN
            SPECS_DIR = $ResolvedPaths.FEATURE_DIR
            BRANCH = $ResolvedPaths.CURRENT_BRANCH
        }
        $result | ConvertTo-Json -Compress
    } else {
        Write-Output "FEATURE_SPEC: $($ResolvedPaths.FEATURE_SPEC)"
        Write-Output "IMPL_PLAN: $($ResolvedPaths.IMPL_PLAN)"
        Write-Output "SPECS_DIR: $($ResolvedPaths.FEATURE_DIR)"
        Write-Output "BRANCH: $($ResolvedPaths.CURRENT_BRANCH)"
    }
}

if ($PathsOnly) {
    Write-SetupPlanResult -ResolvedPaths $paths -JsonMode:$Json
    exit 0
}

# Ensure the feature directory exists
New-Item -ItemType Directory -Path $paths.FEATURE_DIR -Force | Out-Null

# Copy plan template if plan doesn't already exist
if (Test-Path $paths.IMPL_PLAN -PathType Leaf) {
    if ($Json) {
        [Console]::Error.WriteLine("Plan already exists at $($paths.IMPL_PLAN), skipping template copy")
    } else {
        Write-Output "Plan already exists at $($paths.IMPL_PLAN), skipping template copy"
    }
} else {
    $content = Resolve-TemplateContent -TemplateName 'plan-template' -RepoRoot $paths.REPO_ROOT
    if ($null -ne $content) {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($paths.IMPL_PLAN, $content, $utf8NoBom)
        # Emit the copy status like the bash twin (setup-plan.sh); route to stderr
        # in -Json mode so stdout stays pure JSON, matching the sibling messages.
        if ($Json) {
            [Console]::Error.WriteLine("Copied plan template to $($paths.IMPL_PLAN)")
        } else {
            Write-Output "Copied plan template to $($paths.IMPL_PLAN)"
        }
    } else {
        # Match the bash twin's wording and stream routing (stderr in -Json so
        # stdout stays pure JSON, stdout otherwise), consistent with the sibling
        # "Copied plan template" message above.
        if ($Json) {
            [Console]::Error.WriteLine("Warning: Plan template not found")
        } else {
            Write-Output "Warning: Plan template not found"
        }
        # Create a basic plan file if template doesn't exist
        New-Item -ItemType File -Path $paths.IMPL_PLAN -Force | Out-Null
    }
}

Write-SetupPlanResult -ResolvedPaths $paths -JsonMode:$Json
