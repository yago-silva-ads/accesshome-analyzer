"""
AccessHome Analyzer — Script de Deploy AWS
Automatiza o deploy da infraestrutura via CloudFormation + Lambda.

Autor: Yago Santos Silva
Uso: python deploy.py --env dev --region us-east-1
"""

import argparse
import subprocess
import os
import sys
import zipfile
import shutil
from pathlib import Path


def create_lambda_zip(output_path: str = "lambda_package.zip"):
    """Empacota o código Lambda em um .zip para deploy."""
    print("📦 Empacotando Lambda...")
    
    files_to_include = [
        "lambda_handler.py",
        "scan_engine.py",  # Se existir
    ]
    
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_include:
            if os.path.exists(f):
                zf.write(f)
                print(f"  ✓ {f}")
    
    print(f"  → {output_path} ({os.path.getsize(output_path) / 1024:.1f} KB)")
    return output_path


def deploy_cloudformation(env: str, region: str):
    """Deploy do template CloudFormation."""
    stack_name = f"accesshome-analyzer-{env}"
    template_path = "template.json"
    
    print(f"\n🚀 Deploy CloudFormation: {stack_name}")
    print(f"   Região: {region}")
    print(f"   Ambiente: {env}")
    
    cmd = [
        "aws", "cloudformation", "deploy",
        "--template-file", template_path,
        "--stack-name", stack_name,
        "--parameter-overrides",
        f"ProjectName=accesshome-analyzer",
        f"Environment={env}",
        "--capabilities", "CAPABILITY_IAM",
        "--region", region,
        "--no-fail-on-empty-changeset",
    ]
    
    print(f"\n   Executando: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("   ✅ Stack criado/atualizado com sucesso!")
    else:
        print(f"   ❌ Erro: {result.stderr}")
        sys.exit(1)


def update_lambda_code(env: str, region: str):
    """Atualiza o código da Lambda function."""
    function_name = f"accesshome-analyzer-scan-{env}"
    zip_path = create_lambda_zip()
    
    print(f"\n⬆️  Atualizando Lambda: {function_name}")
    
    cmd = [
        "aws", "lambda", "update-function-code",
        "--function-name", function_name,
        "--zip-file", f"fileb://{zip_path}",
        "--region", region,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("   ✅ Lambda atualizada!")
    else:
        print(f"   ❌ Erro: {result.stderr}")
    
    # Limpar zip
    os.remove(zip_path)


def get_stack_outputs(env: str, region: str):
    """Recupera os outputs do CloudFormation (URLs, nomes)."""
    stack_name = f"accesshome-analyzer-{env}"
    
    cmd = [
        "aws", "cloudformation", "describe-stacks",
        "--stack-name", stack_name,
        "--region", region,
        "--query", "Stacks[0].Outputs",
        "--output", "table",
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\n📋 Outputs da Stack:")
        print(result.stdout)
    else:
        print(f"   ⚠️ Não foi possível recuperar outputs: {result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Deploy AccessHome Analyzer na AWS")
    parser.add_argument("--env", "-e", default="dev", choices=["dev", "prod"])
    parser.add_argument("--region", "-r", default="us-east-1")
    parser.add_argument("--only-lambda", action="store_true", help="Atualizar apenas o código Lambda")
    parser.add_argument("--only-infra", action="store_true", help="Deploy apenas da infraestrutura")
    
    args = parser.parse_args()
    
    print("╔══════════════════════════════════════════════╗")
    print("║  AccessHome Analyzer — AWS Deploy            ║")
    print("╚══════════════════════════════════════════════╝")
    
    if not args.only_lambda:
        deploy_cloudformation(args.env, args.region)
    
    if not args.only_infra:
        update_lambda_code(args.env, args.region)
    
    get_stack_outputs(args.env, args.region)
    
    print("\n✅ Deploy completo!")
    print(f"\n💡 Próximo passo:")
    print(f"   Teste a API: curl -X POST https://API_URL/api/scan -d '{{\"url\":\"https://demo.home-assistant.io\"}}'")


if __name__ == "__main__":
    main()
