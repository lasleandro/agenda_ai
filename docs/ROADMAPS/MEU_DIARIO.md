- Features para o futuro:
-- Associar clientes a endereços (de quadras, salão etc)
-- Para tênis, mostrar as quadras
-- Módulo financeiro
-- Pensando em nichar para tênis primeiro, chamaria "meucoach"
-- Criar área de gestão de quadra -> horário -> grupo -> aluno
-- Profissional precisa ter a opção de começar definindo os horários que ele tem 
disponível em cada quadra, por exemplo.
-- Pensar num fluxo de config conversacional para o prof
-- Pensar num otimizador de ganho/what if cenários


- Fazer a agenda compatível com o Google Agenda e Outlook Calendar, para replicar os eventos nesses padrões de mercado.


Senhas de teste: 
admin@agenda.ai / agenda-dev-2026 — platform admin, lands on the tile grid
joao@agenda.ai / agenda-dev-2026 — direct professional login (the existing "Joao" tenant)






2026-08-05

- Após as implementação básicas de plataforma, derivar tools para agentes (ROADMAP criado docs/ROADMAPS/operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md)


- Propagar valores R$/h herdados para serem exibidos na tela de cliente


- ver as conversas não finalizadas no Codex (acabaram os créditos)



- Pensar em construir uma tela de fila/demanda/clientes que querem entrar em algum horário que não tem liberado ainda. (implementado! 2026-08-09)

- Criar a "visão dinheiro" na Agenda, onde o user vê quanto dinheiro por slot tem alocado


2026-08-07


- Criar um monitoramento de aulas canceladas para armazenar o número de reposições por aluno (precisa verificar se o aluno é fixo) (implementado! 2026-08-09)



- Pensar em criar otimização de rota


- Roadmap (ainda não implementado) de reposição de aula e aula cortesia: docs/ROADMAPS/makeup_class_credits_roadmap_v0.1_2026-08-07.md (implementado! 2026-08-09)



- Implementado o docs/ROADMAPS/makeup_class_credits_roadmap_v0.1_2026-08-07.md (implementado! 2026-08-09)



- Avaliando mover a parte de definição da carga horária diária, definição de tempo limite para cancelamento com reposição de aula etc para uma sessão dedicada tipo "Minhas Regras", ou então mudar o nome de "Financeiro" para "Minha Operação" ou "Meu Negócio". (implementado! 2026-08-09)



- Acrescentar, paralelamente à aula, a categoria eventos (torneio, oficina etc), onde o valor pode ser inputado durante a criação do evento.


2026-08-09

- Sistema de notificação (plataforma + chat): "o aluino tal está procurando vaga desde xx. Tem alguma resposta pra ele?". "Vc ainda não respondeu o aluno tal." etc. Com a possibilidade do user cancelar a notificação para clientes específicos (ele pode nao querer responder um ou outro)




- Modificar a definição de locais: o usuário não precisa definir de antemão o  tipo de aula (individual, grupo, nível) quando define um local. O local é mais um default para saber onde estará, um shadow card. O que define esses outros parâmetros é o evento em particular que acontecerá no slot.
(pensar sobre)



- Futura funcionalidade: "me lembra amanhã de falar com fulano" -- automação de lembretes





2026-08-15
- várias melhorias no simulador e na marcação de eventos na agenda
- pré-implementação de docs/ROADMAPS/place_stays_and_schedule_overlay_roadmap_v0.1_2026-08-15.md



2026-08-16
- implementado: docs/ROADMAPS/place_stays_and_schedule_overlay_roadmap_v0.1_2026-08-15.md
- pre-implementação de docs/ROADMAPS/scheduled_tasks_daily_agenda_roadmap_v0.1_2026-08-16.md
- Adicionar cancelamento de aula por evento climático/chuva -> reposição automática

- Pensar em um report financeiro semanal para o tenant
- churn
- ranking alunos com mais reposição/cancelamento



2026-08-19

- Começando a implementar docs/ROADMAPS/pricing_model_unification_tracking_v0.1_2026-08-19.md
- finalizado, junto com vários outros ajustes de ux
- O que falta: re-definir o comportamento da formação de grupos: instrutor deveria ser capaz de promover slots a aula em grupo, e também criar horários de grupo, a serem preenchidos oportunamente



2026-08-21
- várias melhorias implementadas na área de financeiro e simulador
- roadmap de sistema de recomendação de otimização de agenda criado: docs/ROADMAPS/agenda_revenue_recommendations_roadmap_v0.1_2026-08-21.md
- Criado um roadmap para a dinamica de conversão de slots em aula em grupo: docs/ROADMAPS/group_capacity_and_slot_promotion_roadmap_v0.1_2026-08-21.md 
