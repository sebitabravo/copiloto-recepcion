# Seed idempotente del Copiloto de Recepción. Se ejecuta con `rails runner` dentro del contenedor chatwoot.
# Imprime líneas "RUNTIME_VAR CLAVE=VALOR" que scripts/seed-chatwoot.sh vuelca al archivo .env.runtime.

demo_password = ENV.fetch('DEMO_PASSWORD')
webhook_secret = ENV.fetch('WEBHOOK_SECRET')
copiloto_url = ENV.fetch('COPILOTO_INTERNAL_URL', 'http://copiloto:8100')
panel_url = "#{ENV.fetch('COPILOTO_PANEL_URL', 'http://localhost:8100/panel')}?token=#{ENV.fetch('PANEL_TOKEN')}"
landing_url = ENV.fetch('LANDING_URL', 'http://localhost:8080')

account = Account.find_or_create_by!(name: 'Hotel Bordeluz (demo)')
account.update!(locale: 'es')

def upsert_user(account, name:, email:, role:, password:)
  user = User.find_by(email: email)
  if user.nil?
    user = User.new(name: name, display_name: name, email: email, password: password,
                    password_confirmation: password, confirmed_at: Time.current)
    user.skip_confirmation! if user.respond_to?(:skip_confirmation!)
    user.save!
  else
    user.update!(password: password, password_confirmation: password)
  end
  au = AccountUser.find_or_initialize_by(account: account, user: user)
  au.role = role
  au.save!
  user
end

admin = upsert_user(account, name: 'Gerencia Demo', email: 'gerencia@bordeluz-demo.test', role: :administrator,
                             password: demo_password)
rec1 = upsert_user(account, name: 'Recepción Turno Día', email: 'recepcion1@bordeluz-demo.test', role: :agent,
                            password: demo_password)
rec2 = upsert_user(account, name: 'Recepción Turno Tarde', email: 'recepcion2@bordeluz-demo.test', role: :agent,
                            password: demo_password)

labels = {
  'faq' => '#2E7D32', 'comercial' => '#1565C0', 'nocturna' => '#6A1B9A',
  'sla-ambar' => '#F9A825', 'sla-vencido' => '#C62828', 'reserva-ia' => '#00897B'
}
labels.each do |title, color|
  label = Label.find_or_initialize_by(account: account, title: title)
  label.color = color
  label.show_on_sidebar = true
  label.save!
end

# Chatwoot normaliza el nombre del team a minúsculas
team = Team.find_or_create_by!(account: account, name: 'recepción') do |t|
  t.description = 'Equipo humano de recepción'
  t.allow_auto_assign = false
end
[rec1, rec2, admin].each { |u| TeamMember.find_or_create_by!(team: team, user: u) }

inbox = account.inboxes.find_by(name: 'Sitio web demo')
if inbox.nil?
  channel = Channel::WebWidget.create!(
    account: account, website_url: landing_url, widget_color: '#8C6A3F',
    welcome_title: 'Copiloto de Recepción · demo Hotel Bordeluz',
    welcome_tagline: 'Prototipo académico INNOVA3. Respondemos al tiro.',
    pre_chat_form_enabled: false, reply_time: 'in_a_few_minutes'
  )
  inbox = Inbox.create!(account: account, channel: channel, name: 'Sitio web demo',
                        greeting_enabled: false, enable_auto_assignment: false)
end
# No se pide correo: datos mínimos (R6)
inbox.update!(enable_email_collect: false)
[rec1, rec2, admin].each { |u| InboxMember.find_or_create_by!(inbox: inbox, user: u) }

bot = AgentBot.find_or_initialize_by(account: account, name: 'Copiloto de Recepción')
bot.description = 'Asistente determinista de recepción (sin LLM)'
bot.outgoing_url = "#{copiloto_url}/webhooks/chatwoot"
bot.save!
bot.update_columns(secret: webhook_secret) if bot.secret != webhook_secret
bot.reload
abi = AgentBotInbox.find_or_initialize_by(inbox: inbox, agent_bot: bot)
abi.status = :active
abi.save!

# Inbox de WhatsApp (canal API): lo alimenta wa_bridge con los mensajes de OpenWA. Mismo AgentBot que el widget,
# así que el copiloto responde igual y el SLA no cambia. Se crea con WA_BRIDGE_URL (make wa-up);
# si ya existe, un seed normal lo conserva y vuelve a exportar sus variables.
wa_bridge_url = ENV['WA_BRIDGE_URL']
wa_inbox = account.inboxes.find_by(name: 'WhatsApp demo')
if wa_bridge_url.present?
  if wa_inbox.nil?
    wa_channel = Channel::Api.create!(account: account, webhook_url: "#{wa_bridge_url}/webhooks/chatwoot")
    wa_inbox = Inbox.create!(account: account, channel: wa_channel, name: 'WhatsApp demo',
                             greeting_enabled: false, enable_auto_assignment: false)
  else
    wa_inbox.channel.update!(webhook_url: "#{wa_bridge_url}/webhooks/chatwoot")
  end
end
if wa_inbox
  wa_inbox.update!(enable_email_collect: false)
  [rec1, rec2, admin].each { |u| InboxMember.find_or_create_by!(inbox: wa_inbox, user: u) }
  wa_abi = AgentBotInbox.find_or_initialize_by(inbox: wa_inbox, agent_bot: bot)
  wa_abi.status = :active
  wa_abi.save!
end

app = DashboardApp.find_or_initialize_by(account: account, title: 'Copiloto')
app.user = admin
app.content = [{ 'type' => 'frame', 'url' => panel_url }]
app.save!

# Sin esto Chatwoot redirige siempre a /installation/onboarding en una instalación nueva
::Redis::Alfred.delete(::Redis::Alfred::CHATWOOT_INSTALLATION_ONBOARDING)

puts "RUNTIME_VAR CHATWOOT_ACCOUNT_ID=#{account.id}"
puts "RUNTIME_VAR CHATWOOT_ADMIN_TOKEN=#{admin.access_token.token}"
puts "RUNTIME_VAR CHATWOOT_BOT_TOKEN=#{bot.access_token.token}"
puts "RUNTIME_VAR CHATWOOT_WEBSITE_TOKEN=#{inbox.channel.website_token}"
puts "RUNTIME_VAR CHATWOOT_TEAM_ID=#{team.id}"
if wa_inbox
  puts "RUNTIME_VAR CHATWOOT_WA_INBOX_IDENTIFIER=#{wa_inbox.channel.identifier}"
  puts "RUNTIME_VAR CHATWOOT_WA_INBOX_SECRET=#{wa_inbox.channel.secret}"
end
puts 'SEED_OK'
