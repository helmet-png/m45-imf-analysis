# One-time setup: fetch the full TLS certificate chain for the PARSEC isochrone
# service and store it as a local PEM bundle for Python to use.
#
# Why this is needed: stev.oapd.inaf.it does not send its intermediate
# certificate. Windows schannel silently downloads the missing intermediate
# (AIA chasing) so browsers and PowerShell work, but OpenSSL (used by Python)
# does not, so Python fails with CERTIFICATE_VERIFY_FAILED. Capturing the chain
# here keeps certificate verification ON in the pipeline instead of disabling it.
#
# Usage (from repo root):  powershell -ExecutionPolicy Bypass -File .\setup\setup_ca.ps1
#
# NOTE: keep this file pure ASCII. PowerShell 5.1 reads .ps1 as ANSI when there
# is no BOM, so non-ASCII comments corrupt the parse.

$ErrorActionPreference = "Stop"
$targetHost = "stev.oapd.inaf.it"
$repoRoot = Split-Path $PSScriptRoot -Parent
$outFile = Join-Path $repoRoot "certs\parsec_chain.pem"
New-Item -ItemType Directory -Force (Split-Path $outFile) | Out-Null

Write-Host "Connecting to $targetHost ..."
$callback = { param($s, $c, $ch, $e) return $true }
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = $callback
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

$req = [System.Net.HttpWebRequest]::Create("https://$targetHost/cgi-bin/cmd")
$req.Timeout = 60000
$resp = $req.GetResponse()
$leaf = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($req.ServicePoint.Certificate)
$resp.Close()
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null

$chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
$chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
$built = $chain.Build($leaf)
Write-Host "Chain built: $built  ($($chain.ChainElements.Count) elements)"

$sb = New-Object System.Text.StringBuilder
foreach ($el in $chain.ChainElements) {
    $c = $el.Certificate
    Write-Host ("  - " + $c.Subject)
    [void]$sb.AppendLine("# " + $c.Subject)
    [void]$sb.AppendLine("-----BEGIN CERTIFICATE-----")
    $b64 = [Convert]::ToBase64String($c.RawData, [Base64FormattingOptions]::InsertLineBreaks)
    [void]$sb.AppendLine($b64)
    [void]$sb.AppendLine("-----END CERTIFICATE-----")
}
[IO.File]::WriteAllText($outFile, $sb.ToString())
Write-Host ""
Write-Host "Wrote $outFile"
