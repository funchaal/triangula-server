"""
Serviço de Notificação
Dispara e-mail para todos os membros do ciclo + BCC para o log técnico.
"""
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from core.config import get_settings

async def notify_match(r, match: dict, users: list):
    settings = get_settings()

    # Monta mapa username → email a partir da lista de users
    email_map = {u["username"]: u["email"] for u in users if u and u.get("email") and u.get("username")}
    recipients = list(email_map.values())

    if not recipients:
        return

    chain_display = " ➔ ".join(
        step.get("base_id", "?") for step in match["chain"]
    ) + f" ➔ {match['chain'][0].get('base_id', '?')}"

    # Adicione a URL do seu frontend aqui ou puxe do settings
    frontend_url = "http://localhost:5173" 
    
    subject   = f"[Triangula] Permuta Encontrada: {chain_display}"
    body_html = _build_email_html(match, chain_display, frontend_url)

    _send_email(
        settings=settings,
        to=recipients,
        bcc=settings.bcc_email,
        subject=subject,
        html=body_html,
        bcc_attachment=json.dumps(match, indent=2, ensure_ascii=False),
    )


async def notify_password_reset(email: str, username: str, token: str, frontend_url: str):
    settings = get_settings()
    reset_link = f"{frontend_url}/login?token={token}"
    subject = "[Triangula] Recuperação de Senha"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f8fafc; padding: 30px 10px;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color: #2563eb; padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 26px; letter-spacing: 1px;">▲ Triangula</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #0f172a; margin-top: 0; font-size: 22px;">Olá, {username}!</h2>
                                <p style="color: #475569; line-height: 1.6; font-size: 16px;">Recebemos uma solicitação para redefinir a senha da sua conta no <strong>Triangula</strong>.</p>
                                <p style="color: #475569; line-height: 1.6; font-size: 16px;">Clique no botão abaixo para criar uma nova senha. Por motivos de segurança, este link é válido por <strong>1 hora</strong>.</p>
                                
                                <div style="text-align: center; margin: 35px 0;">
                                    <a href="{reset_link}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 16px; letter-spacing: 0.5px;">Redefinir Minha Senha</a>
                                </div>
                                
                                <p style="color: #64748b; font-size: 14px; line-height: 1.5; border-top: 1px solid #e2e8f0; padding-top: 25px; margin-bottom: 0;">
                                    Se você não solicitou essa alteração, nenhuma ação é necessária. Sua senha continuará a mesma e sua conta está segura.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color: #f1f5f9; padding: 20px; text-align: center;">
                                <p style="color: #64748b; margin: 0; font-size: 13px; font-weight: bold;">Triangula</p>
                                <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 12px;">Sistema de Gestão de Permutas</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    _send_email(
        settings=settings,
        to=[email],
        bcc=settings.bcc_email,
        subject=subject,
        html=body_html,
        bcc_attachment="Password reset requested.",
    )


def _send_email(settings, to: list, bcc: str, subject: str, html: str, bcc_attachment: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.smtp_user
    msg["To"]      = ", ".join(to)
    msg["Bcc"]     = bcc

    msg.attach(MIMEText(html, "html", "utf-8"))

    audit_part = MIMEText(bcc_attachment, "plain", "utf-8")
    audit_part.add_header("Content-Disposition", "attachment", filename="match_dump.json")
    msg.attach(audit_part)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(settings.smtp_user, to + [bcc], msg.as_string())
    except Exception as e:
        print(f"[notify_match] Falha ao enviar e-mail: {e}")


def _build_email_html(match: dict, chain_display: str, frontend_url: str) -> str:
    # Monta a lista de usuários com um design de "cards" sutis
    steps_html = "".join(
        f"""
        <tr>
            <td style="padding: 15px; border-bottom: 1px solid #e2e8f0;">
                <div style="font-size: 16px; color: #0f172a; font-weight: bold;">{step.get('name', step.get('username', '?'))}</div>
                <div style="font-size: 14px; color: #64748b; margin-top: 4px;">Chave: {step.get('user_key', 'N/A')}</div>
                <div style="font-size: 14px; color: #2563eb; font-weight: bold; margin-top: 4px;">Base Atual: {step.get('base_id', '?')}</div>
            </td>
        </tr>
        """
        for step in match["chain"]
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f8fafc; padding: 30px 10px;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color: #2563eb; padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 26px; letter-spacing: 1px;">▲ Triangula</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #0f172a; margin-top: 0; font-size: 22px;">Nova Permuta Encontrada! 🎉</h2>
                                <p style="color: #475569; line-height: 1.6; font-size: 16px;">O algoritmo do Triangula identificou um novo ciclo de permuta compatível com seus interesses.</p>
                                
                                <table width="100%" cellpadding="0" cellspacing="0" style="margin: 25px 0;">
                                    <tr>
                                        <td style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 15px 20px; border-radius: 0 8px 8px 0;">
                                            <p style="margin: 0; color: #1e3a8a; font-weight: bold; font-size: 15px; text-align: center;">{chain_display}</p>
                                        </td>
                                    </tr>
                                </table>
                                
                                <h3 style="color: #334155; margin-top: 30px; margin-bottom: 15px; font-size: 18px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;">Membros do Ciclo:</h3>
                                
                                <table width="100%" cellpadding="0" cellspacing="0" style="border: 1px solid #e2e8f0; border-radius: 8px; border-collapse: separate; overflow: hidden;">
                                    {steps_html}
                                </table>
                                
                                <div style="text-align: center; margin-top: 40px;">
                                    <a href="{frontend_url}" style="display: inline-block; background-color: #10b981; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 16px; letter-spacing: 0.5px;">Acessar o Sistema</a>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color: #f1f5f9; padding: 20px; text-align: center;">
                                <p style="color: #64748b; margin: 0; font-size: 13px;">Este é um e-mail automático, por favor não responda.</p>
                                <p style="color: #94a3b8; margin: 8px 0 0 0; font-size: 11px; font-family: monospace;">Match ID: {match.get('id', '?')}</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """