"""
Serviço de Notificação
Dispara e-mail para todos os membros do ciclo + BCC para o log técnico.
"""
import asyncio

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

async def notify_match(
    match: dict, 
    users: list, 
    frontend_url: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    bcc_email: str = ""
):
    # Monta mapa username → email a partir da lista de users
    email_map = {u["username"]: u["email"] for u in users if u and u.get("email") and u.get("username")}
    recipients = list(email_map.values())

    if not recipients:
        return

    chain_display = " ➔ ".join(
        step.get("base_id", "?") for step in match["chain"]
    ) + f" ➔ {match['chain'][0].get('base_id', '?')}"
    
    subject   = f"[Triangula] Permuta Encontrada: {chain_display}"
    body_html = _build_email_html(match, chain_display, frontend_url)

    await asyncio.to_thread(
        _send_email,
        to=recipients,
        bcc=bcc_email,
        subject=subject,
        html=body_html,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass
    )


async def notify_password_reset(
    email: str, 
    username: str, 
    token: str, 
    frontend_url: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str
):
    reset_link = f"{frontend_url}/login?token={token}"
    subject = "[Triangula] Recuperação de Senha"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #03072a; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #03072a; padding: 30px 10px;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #13204c; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                        <tr>
                            <td style="padding: 30px; text-align: center; border-bottom: 1px solid #1e293b;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: 1px;">▲ Triangula</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Olá, {username}!</h2>
                                <p style="color: #cbd5e1; line-height: 1.6; font-size: 15px;">Recebemos uma solicitação para redefinir a senha da sua conta no <strong>Triangula</strong>.</p>
                                <p style="color: #cbd5e1; line-height: 1.6; font-size: 15px;">Clique no botão abaixo para criar uma nova senha. Este link é válido por <strong>1 hora</strong>.</p>
                                
                                <div style="text-align: center; margin: 35px 0;">
                                    <a href="{reset_link}" style="display: inline-block; background-color: #10b981; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 16px;">Redefinir Minha Senha</a>
                                </div>
                                
                                <p style="color: #94a3b8; font-size: 13px; line-height: 1.5; border-top: 1px solid #1e293b; padding-top: 25px; margin-bottom: 0;">
                                    Se você não solicitou essa alteração, desconsidere este e-mail.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color: #0b122e; padding: 20px; text-align: center;">
                                <p style="color: #64748b; margin: 0; font-size: 12px;">Triangula - Sistema de Gestão de Permutas</p>
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
        to=[email],
        bcc="",
        subject=subject,
        html=body_html,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass
    )


def _send_email(
    to: list, 
    bcc: str, 
    subject: str, 
    html: str, 
    smtp_host: str, 
    smtp_port: int, 
    smtp_user: str, 
    smtp_pass: str
):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = ", ".join(to)
    
    if bcc:
        msg["Bcc"] = bcc

    # Anexa apenas o HTML (sem arquivos soltos para evitar spam)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            
            # Monta a lista final de destinatários para o envelope do SMTP
            all_recipients = to.copy()
            if bcc:
                all_recipients.append(bcc)
                
            server.sendmail(smtp_user, all_recipients, msg.as_string())
            print(f"[Notificação] E-mail enviado para {to}")
    except Exception as e:
        print(f"[Notificação] Falha ao enviar e-mail: {e}")


def _build_email_html(match: dict, chain_display: str, frontend_url: str) -> str:
    steps_html = "".join(
        f"""
        <tr>
            <td style="padding: 15px; border-bottom: 1px solid #1e293b;">
                <div style="font-size: 15px; color: #ffffff; font-weight: bold;">{step.get('name', step.get('username', '?'))}</div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">Chave: {step.get('key', 'N/A')}</div>
                <div style="font-size: 13px; color: #60a5fa; font-weight: bold; margin-top: 4px;">Base Atual: {step.get('base_id', '?')}</div>
            </td>
        </tr>
        """
        for step in match["chain"]
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #03072a; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #03072a; padding: 30px 10px;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #13204c; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                        <tr>
                            <td style="padding: 30px; text-align: center; border-bottom: 1px solid #1e293b;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: 1px;">▲ Triangula</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Nova Permuta Encontrada! 🎉</h2>
                                <p style="color: #cbd5e1; line-height: 1.6; font-size: 15px;">Identificamos um novo ciclo de permuta compatível com seus interesses.</p>
                                
                                <table width="100%" cellpadding="0" cellspacing="0" style="margin: 25px 0;">
                                    <tr>
                                        <td style="background-color: #0b122e; border-left: 4px solid #3b82f6; padding: 15px 20px; border-radius: 0 8px 8px 0;">
                                            <p style="margin: 0; color: #60a5fa; font-weight: bold; font-size: 15px; text-align: center;">{chain_display}</p>
                                        </td>
                                    </tr>
                                </table>
                                
                                <h3 style="color: #ffffff; margin-top: 30px; margin-bottom: 15px; font-size: 16px;">Membros do Ciclo:</h3>
                                
                                <table width="100%" cellpadding="0" cellspacing="0" style="border: 1px solid #1e293b; border-radius: 8px; border-collapse: separate; overflow: hidden;">
                                    {steps_html}
                                </table>
                                
                                <div style="text-align: center; margin-top: 40px;">
                                    <a href="{frontend_url}" style="display: inline-block; background-color: #10b981; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 16px;">Acessar o Sistema</a>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color: #0b122e; padding: 20px; text-align: center;">
                                <p style="color: #64748b; margin: 0; font-size: 12px;">Este é um e-mail automático, por favor não responda.</p>
                                <p style="color: #475569; margin: 8px 0 0 0; font-size: 11px; font-family: monospace;">Match ID: {match.get('id', '?')}</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """