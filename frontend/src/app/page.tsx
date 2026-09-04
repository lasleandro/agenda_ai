import type { Metadata } from "next";
import Image from "next/image";
import { Manrope, DM_Mono } from "next/font/google";
import { LandingEnterCta } from "@/components/landing/landing-enter-cta";
import { LandingRequestCta } from "@/components/landing/landing-request-cta";
import "./landing.css";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-manrope",
  display: "swap",
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-dm-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tennis OS — Seu assistente de quadra",
  description:
    "O Lob organiza a rotina de professores de tênis a partir das conversas no WhatsApp.",
};

const steps = [
  {
    n: "01",
    title: "Converse",
    text: "Continue usando o WhatsApp normalmente com seus alunos.",
  },
  {
    n: "02",
    title: "Deixe com o Lob",
    text: "Horários, alterações e pendências importantes deixam de ficar perdidos nas conversas.",
  },
  {
    n: "03",
    title: "Volte pro jogo",
    text: "Tenha uma visão clara da sua agenda e da sua semana, sem alimentar manualmente mais um sistema.",
  },
  {
    n: "04",
    title: "Converse com o Lob",
    text: "“Tenho horário livre amanhã à tarde?” ou “Encontre uma reposição para a Marina.” Para alterações, o Lob mostra uma prévia antes da confirmação.",
  },
];

const benefits = [
  { n: "01", title: "Tempo", text: "Menos tempo procurando mensagens e atualizando sistemas." },
  { n: "02", title: "Controle", text: "Uma visão organizada do que foi combinado com cada aluno." },
  { n: "03", title: "Tranquilidade", text: "Menos coisas para guardar na cabeça durante o dia." },
  { n: "04", title: "Previsibilidade", text: "Agenda e operação mais claras para planejar a semana." },
];

const activationSteps = [
  { n: "01", title: "Solicite seu acesso", text: "Conte um pouco sobre sua operação para iniciar seu cadastro." },
  { n: "02", title: "Cadastre o essencial", text: "Adicione alunos, locais, horários e regras básicas." },
  { n: "03", title: "Conecte o WhatsApp Business", text: "Autorize o número que você já usa para falar com seus alunos." },
  { n: "04", title: "Salve o contato do Lob", text: "Adicione o número privado do seu assistente ao WhatsApp." },
  { n: "05", title: "Siga conversando normalmente", text: "O Lob acompanha a operação e fica disponível quando você precisar." },
];

const modules = [
  { n: "01", title: "Agenda", text: "Visualize sua semana, aulas avulsas e horários fixos em um só lugar." },
  { n: "02", title: "Alunos e grupos", text: "Organize alunos, níveis, turmas e horários recorrentes." },
  { n: "03", title: "Locais", text: "Cadastre as quadras e os espaços em que você trabalha." },
  {
    n: "04",
    title: "Reposições",
    text: "Acompanhe créditos de reposição e receba recomendações de opções de horário.",
  },
  { n: "05", title: "Financeiro", text: "Acompanhe sua receita, ocupação e estime seu potencial." },
  { n: "06", title: "Suas regras", text: "Defina jornada, intervalos e aviso prévio para reposições." },
];

export default function LandingPage() {
  const year = new Date().getFullYear();

  return (
    <div className={`landing-page ${manrope.variable} ${dmMono.variable}`}>
      <header className="site-header">
        <nav className="nav container" aria-label="Navegação principal">
          <a className="brand" href="#inicio" aria-label="Tennis OS, início">
            <Image className="brand-logo" src="/landing/logo.png" alt="" width={90} height={90} priority />
            <span>Tennis OS</span>
          </a>
          <div className="nav-actions">
            <LandingEnterCta className="nav-cta" />
            <LandingRequestCta className="nav-cta nav-request-cta" />
          </div>
        </nav>
      </header>

      <main>
        <section className="hero" id="inicio">
          <div className="court-grid" aria-hidden="true" />
          <div className="container hero-layout">
            <div className="hero-copy">
              <p className="eyebrow">
                <span /> Lob, seu assistente de quadra
              </p>
              <h1>
                Jogando sob pressão?
                <br />
                <em>O Lob resolve.</em>
              </h1>
              <p className="hero-description">
                Sua rotina já acontece no WhatsApp. Continue conversando com seus alunos
                normalmente — o Lob, o agente de IA que é o cérebro do{" "}
                <strong className="brand-highlight">Tennis OS</strong>, ajuda a transformar
                mensagens, horários e pendências em uma operação organizada.
              </p>
              <div className="cta-group hero-actions">
                <LandingRequestCta className="button button-primary" withArrow />
                <LandingEnterCta className="button button-secondary" />
              </div>
            </div>

            <div
              className="hero-product"
              aria-label="Exemplo de como o Lob organiza as conversas"
            >
              <div className="trajectory" aria-hidden="true">
                <svg viewBox="0 0 440 240" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M13 221C99 220 121 33 250 36C332 38 323 166 427 167"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeDasharray="5 7"
                  />
                </svg>
              </div>
              <div className="message-card card-message-one">
                <div className="message-meta">
                  <span className="avatar avatar-blue">M</span> Marina <time>09:12</time>
                </div>
                <p>Podemos manter terça às 15h?</p>
              </div>
              <div className="message-card card-message-two">
                <div className="message-meta">
                  <span className="avatar avatar-sand">J</span> João <time>11:32</time>
                </div>
                <p>Quinta vou viajar. Conseguimos remarcar?</p>
              </div>
              <div className="schedule-card">
                <div className="schedule-header">
                  <span>Agenda da semana</span>
                  <span className="more">•••</span>
                </div>
                <div className="schedule-days">
                  <span>SEG</span>
                  <span className="active-day">
                    TER <b>12</b>
                  </span>
                  <span>QUA</span>
                  <span>QUI</span>
                </div>
                <div className="schedule-event">
                  <time>15:00</time>
                  <div>
                    <strong>Marina Oliveira</strong>
                    <small>Aula individual · Quadra 2</small>
                  </div>
                  <span className="event-dot" />
                </div>
                <div className="schedule-event muted-event">
                  <time>18:00</time>
                  <div>
                    <strong>João Ribeiro</strong>
                    <small>Aguardando remarcação</small>
                  </div>
                  <span className="event-dot" />
                </div>
                <div className="schedule-footer">
                  <span>2 atualizações feitas</span>
                  <span>Ver agenda →</span>
                </div>
              </div>
              <div className="lob-orb" aria-hidden="true">
                <span>L</span>
              </div>
            </div>
          </div>
        </section>

        <section className="problem section" id="conheca">
          <div className="container split-heading">
            <p className="section-kicker">A rotina que você conhece</p>
            <div>
              <h2>
                Você dá aula dia e noite.
                <br />
                Depois ainda precisa administrar tudo.
              </h2>
              <p>
                Durante o dia, seus alunos mandam mensagens para marcar horários, cancelar,
                remarcar, pedir reposição e confirmar pagamentos. No fim, sobra para você
                reconstruir tudo isso na agenda.
              </p>
              <p className="strong-copy">
                O Lob foi pensado para eliminar esse segundo trabalho.
              </p>
            </div>
          </div>
        </section>

        <section className="how section">
          <div className="container">
            <div className="section-intro">
              <p className="section-kicker">Simplicidade</p>
              <h2>
                Você conversa.
                <br />
                O Lob organiza.
              </h2>
            </div>
            <div className="steps">
              {steps.map((step) => (
                <article className="step" key={step.n}>
                  <span className="step-number">{step.n}</span>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="activation section">
          <div className="container">
            <div className="activation-heading">
              <div>
                <p className="section-kicker">Comece sem mudar sua rotina</p>
                <h2>
                  Em poucos passos,
                  <br />
                  <em>o Lob entra no jogo.</em>
                </h2>
              </div>
              <p>
                Configure o essencial, conecte seu WhatsApp Business e continue falando com seus
                alunos como sempre.
              </p>
            </div>
            <ol className="activation-grid">
              {activationSteps.map((step) => (
                <li key={step.n}>
                  <span>{step.n}</span>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="benefits section">
          <div className="container">
            <div className="benefits-heading">
              <p className="section-kicker">Mais espaço para o que importa</p>
              <h2>
                Menos administração.
                <br />
                <em>Mais tempo em quadra.</em>
              </h2>
            </div>
            <div className="benefit-grid">
              {benefits.map((benefit) => (
                <article key={benefit.n}>
                  <span>{benefit.n}</span>
                  <h3>{benefit.title}</h3>
                  <p>{benefit.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="platform section">
          <div className="container">
            <div className="platform-heading">
              <div>
                <p className="section-kicker">E ainda mais:</p>
                <h2>
                  Mais do que uma agenda.
                  <br />
                  O sistema da sua operação.
                </h2>
              </div>
              <p>
                O <strong className="brand-highlight">Tennis OS</strong> reúne o que acontece
                dentro e fora da quadra. O Lob é o assistente que ajuda você a manter tudo em
                movimento.
              </p>
            </div>
            <div className="module-grid">
              {modules.map((module) => (
                <article className="module-card" key={module.n}>
                  <span className="module-index">{module.n}</span>
                  <h3>{module.title}</h3>
                  <p>{module.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="final-cta">
          <div className="container final-content">
            <p className="section-kicker">
              <strong className="brand-highlight brand-highlight-light">Tennis OS</strong> · com
              Lob
            </p>
            <h2>
              Sua operação já está no WhatsApp.
              <br />
              <em>Por que sair dele?</em>
            </h2>
            <p>
              Estamos construindo uma forma mais leve de organizar a rotina de quem vive em
              quadra.
            </p>
            <div className="cta-group final-actions">
              <LandingRequestCta className="button button-light" withArrow />
              <LandingEnterCta className="button button-light-outline" />
            </div>
          </div>
        </section>
      </main>

      <footer className="footer">
        <div className="container footer-content">
          <a className="brand" href="#inicio">
            <Image className="brand-logo" src="/landing/logo.png" alt="" width={30} height={30} />
            <span>Tennis OS</span>
          </a>
          <p>O cérebro da sua operação.</p>
          <a className="footer-email" href="mailto:contato@tennisos.com.br">
            contato@tennisos.com.br
          </a>
          <p>
            © {year} <strong>Tennis OS</strong>. Em desenvolvimento.
          </p>
        </div>
      </footer>

      <a
        className="whatsapp-button"
        href="https://wa.me/5511918796827?text=Ol%C3%A1%2C%20quero%20conhecer%20o%20Tennis%20OS."
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Falar com o Tennis OS pelo WhatsApp"
      >
        <Image src="/landing/whatsapp.png" alt="" width={62} height={62} />
        <span className="sr-only">Falar pelo WhatsApp</span>
      </a>
    </div>
  );
}
