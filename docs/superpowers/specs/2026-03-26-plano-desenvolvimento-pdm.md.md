# Plano de Desenvolvimento do SWAT-PDM
**Nome interno:** SWAT-PDM (Sistema de Gestão de Dados de Produção Automática)  
**Data da última atualização:** 22 de Março de 2026  
**Status:** Em desenvolvimento ativo – Fase de consolidação do MVP + expansão para funcionalidades Professional-like  

## 1. Objetivo Geral
Criar um sistema PDM leve, integrado ao fluxo de produção da empresa, que substitua o controlo manual de ficheiros SolidWorks e melhore a colaboração, rastreabilidade e reutilização de designs.

**Inspiração principal:** SOLIDWORKS PDM (Standard + Professional), mas adaptado à realidade da empresa (pequena/média equipa, foco em SolidWorks, servidor Windows partilhado, sem necessidade inicial de multi-site ou ERP full).

## 2. Estado Atual (Março 2026)

### Já implementado (base sólida do MVP)
- Launcher central em **PyQt6** (substitui scripts bat + Tkinter)
- Criação de projetos via Wizard (pastas 01-Engineering / 02-Production / 03-Documentation + templates)
- Vista Explorer-like 3 painéis:
  - Árvore de diretórios (esquerda)
  - Tabela central com colunas: Name, Status, Revision, Locked By, Date
  - Painel direito (Details) com abas Preview/Properties/History
- Check-Out / Check-In funcional:
  - Bloqueio via atributo Read-Only + registo na BD
  - Cor verde (meu lock), vermelho (outro utilizador), branco (livre)
  - Incremento de versão simples + comentário obrigatório no Check-In
- Pesquisa básica (QLineEdit + filtro no modelo da tabela)
- Histórico de ações (tabela history + widget no painel direito)
- Lifecycle básico (status: In Design → Approved)
- Lançamento de ferramentas legadas via subprocess (ex: Exporter)

### Base de dados atual (`swat_pdm.db` – SQLite)
- Tabelas principais: projects, locks, history
- Coluna `status` adicionada em locks

## 3. Roadmap – Prioridades 2026

### Fase Atual: MVP Completo & Estabilidade (Q2 2026)
Objetivo: Tornar o sistema utilizável em produção diária por toda a equipa de engenharia.

- [ ] Refinar a pesquisa (Task prioritária #1)
  - Suporte a múltiplos critérios (nome + material + revisão + estado)
  - Match types: exact, contains, starts with, wildcard (*)
  - Histórico das últimas 5 pesquisas (dropdown)
  - **Search Favorites** (salvar buscas + opção “Run on Load” ao abrir o vault)

- [ ] Melhorar o painel de detalhes
  - Aba Properties: mostrar/le editar custom properties do SolidWorks via API COM (se possível) ou parsing básico
  - Aba Preview: thumbnail + zoom simples (usar QPixmap ou eDrawings ActiveX se viável)

- [ ] Versionamento mais robusto
  - Criar cópia da versão anterior em subpasta `_history/vXX` no Check-In
  - Mostrar lista de versões disponíveis no painel direito

- [ ] Segurança & UX
  - Avisos claros quando ficheiro está locked por outro utilizador
  - Timeout de lock automático após X horas (configurável)
  - Log de todas as ações num ficheiro .log + tabela audit

### Fase 2: Funcionalidades Standard-like (Q3–Q4 2026)

- [ ] Workflows simples configuráveis
  - Estados: In Design → Review → Approved → Released → Archived
  - Transições com ações (ex: gerar PDF no Approved → Released)

- [ ] Tarefas automáticas básicas
  - Gerar PDF/DXF/STEP neutro no Check-In ou em transição específica
  - Executar via subprocess nos exporters existentes

- [ ] Data Cards básicos
  - Formulário ao Check-In para preencher Número de peça, Material, Descrição, etc.
  - Guardar em ficheiro .sldprt/.sldasm (custom properties) + na BD

- [ ] Colunas dinâmicas na tabela
  - Mostrar valores de custom properties (ex: Material, Part Number)

### Fase 3: Caminho para Professional-like (2027+)

- Acesso Web (browser) via Flask/FastAPI + frontend React/Vue
- Replicação entre servidores (para filiais)
- Integração com ERP (export BOM + números de peça)
- Suporte multi-CAD (se aparecer Inventor/AutoCAD na empresa)
- Relatórios (quem alterou o quê, ficheiros pendentes de aprovação)

## 4. Stack Tecnológico Confirmado

- Linguagem: **Python 3.11+**
- GUI: **PyQt6** (mantém-se por ser nativo, rápido e familiar no Windows)
- Base de dados: **SQLite** (fácil, sem servidor, suficiente para 50 utilizadores)
- Integração SolidWorks: pywin32 + COM API (quando necessário para properties/preview)
- Outros: os, shutil, subprocess, win32api (atributos de ficheiro)

## 5. Próximas Tarefas Imediatas (próximas 2–4 semanas)

1. Implementar **pesquisa avançada** (múltiplos filtros + favorites)
2. Adicionar **version backup** físico no Check-In
3. Criar **formulário Data Card simples** no Check-In
4. Testar com 3–5 utilizadores reais em ambiente partilhado (\\Server\Projetos)
5. Documentar fluxos completos (com screenshots) para treino da equipa

## 6. Perguntas / Decisões Pendentes para Avançar

- Queres manter SQLite para sempre ou migrar para PostgreSQL quando crescer?
- Integração COM com SolidWorks (pywin32): vale a pena investir agora para ler properties/preview?
- Gerar PDFs/DXF automaticamente: qual o executor preferido (o exporter atual ou SolidWorks Task Scheduler)?
- Formato de versão: manter `v01`, `v02`… ou adotar A, B, C… ou data-based?
- Queres começar a prototipar o acesso Web já em paralelo (mesmo que simples)?

Avança fase a fase.  
Prioridade máxima agora: **tornar a pesquisa poderosa e o versionamento seguro** — são os pontos que mais vão reduzir erros e aumentar confiança da equipa.
