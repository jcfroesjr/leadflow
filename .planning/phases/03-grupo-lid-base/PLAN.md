# Phase 3 — Fix @lid Base

**Milestone:** v2.1 Grupo WhatsApp Robusto
**Goal:** Validar + commit + redeploy do fix @lid base (já implementado no workdir 20/05).
**Critical path:** sim — fundação pras Fases 4-9.

## Status no workdir

Implementação completa, sintaxe Python validada via `ast.parse` em todos os arquivos. Aguarda:
1. Verificação visual final (este plano)
2. Commit + push
3. Redeploy Easypanel
4. Smoke test em prod

## Arquivos modificados (workdir)

| Arquivo | Mudança | Linhas chave |
|---------|---------|--------------|
| `app/services/evolution.py` | Parâmetro `lead_lid: str = ""` em `verificar_lead_no_grupo` + match por @lid no loop | 198-302 |
| `app/routers/grupo_webhook.py` | Separa @lid de telefones; heurística unique-aguardando; helper `_salvar_lead_lid` | 16-200 |
| `app/services/grupo_fallback.py` | Helper `_get_lead_lid_for_group` + 6 callers threadeados | 54-87, 252, 294, 320, 460, 596, 1150 |
| `app/routers/confirmacao_agendamento.py` | Caller threadeado no probe D-1 | 289-292 |

## Tasks atômicas

### Task 1: Inspeção final do diff (read-only)
- [ ] Read das 4 mudanças via `git diff` e validar:
  - Probe Evolution: lead_lid case-insensitive + early return em match
  - Webhook: ambiguidade trata >1 lead aguardando como log + skip
  - Helper: query LIKE com `order_by criado_em desc limit 1`
  - confirmacao_agendamento: import do helper + uso

### Task 2: Validação Python
- [ ] `python -c "import ast; ast.parse(...)"` em cada arquivo modificado (✓ já feito)
- [ ] `python -c "from app.services.evolution import verificar_lead_no_grupo"` confirma import
- [ ] `python -c "from app.services.grupo_fallback import _get_lead_lid_for_group, processar_entrada_lead_no_grupo"` confirma import

### Task 3: Smoke test local (opcional, se ambiente .venv disponível)
- [ ] Iniciar backend em modo dev
- [ ] POST mockado pro webhook de grupo com participants=[`<lid>@lid`] + 1 lead aguardando
- [ ] Verificar marker `LEAD_LID:{grupo_jid}:{lid}` salvo
- [ ] Verificar FSM transicionou pra ATIVO

(Skip se .venv não estiver disponível — smoke test em prod basta)

### Task 4: Commit + push
- [ ] `git add` dos 4 arquivos modificados em `leadflow-backend/app/`
- [ ] Commit message:
  ```
  feat(grupo): captura @lid no webhook + probe match alternativo
  
  Resolve causa-raiz dos bugs Luciane/Karla: WhatsApp esconde telefone do
  lead como @lid (Linked ID) por privacidade alta. Sem mapping confiável,
  probe Evolution era chute (cada fix anterior foi trade-off entre falso
  positivo e falso negativo).
  
  Agora:
  - GROUP_PARTICIPANTS_UPDATE webhook separa @lid de telefones limpos;
    heurística unique-aguardando salva marker LEAD_LID:{jid}:{lid}
  - verificar_lead_no_grupo aceita lead_lid como matcher alternativo
  - Helper _get_lead_lid_for_group lê marker antes de cada probe
  - 7 callers threadeados (6 em grupo_fallback.py + 1 em confirmacao_agendamento.py)
  
  Causa Karla 5581988280629 (Liliane 20/05): @lid removido pelo fix de
  18/05 retornava in_group=None → FALLBACK_1_1 mesmo lead no grupo.
  Agora marker LEAD_LID resolve sem trade-off.
  
  NÃO reverte fix Fase 1 18/05 (presunção @lid=True removida) — esta
  mudança é complementar.
  
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- [ ] `cd leadflow-backend && git push`
- [ ] Bump versão em parent repo (se aplicável): `git add leadflow-backend && git commit -m "chore: bump backend pra fix @lid"`

### Task 5: Redeploy Easypanel
- [ ] User: acessar Easypanel painel → Deploy backend (manual)
- [ ] Confirmar via `curl https://leadflow-backend.bqvcbz.easypanel.host/version`

### Task 6: Smoke test em produção
- [ ] Próximo lead novo qualquer empresa (Rejane ou Liliane) que tem privacidade alta
- [ ] Aguardar lead agendar → entrar no grupo
- [ ] Verificar via Supabase: `SELECT conteudo FROM conversas WHERE conteudo LIKE 'LEAD_LID:%' ORDER BY criado_em DESC LIMIT 3` retorna marker novo
- [ ] Verificar FSM ATIVO: `SELECT conteudo FROM conversas WHERE conteudo LIKE 'GRUPO_STATE:%:ATIVO' ORDER BY criado_em DESC LIMIT 3`
- [ ] Verificar logs Easypanel `[VERIFY-LEAD]` mostram lid no match

### Task 7: Backfill Karla manual (last mile desta fase)
- [ ] User executa no Supabase Editor:
  ```sql
  UPDATE conversas SET criado_em = NOW()
  WHERE empresa_id = '6afadc2f-19c4-4c7a-b9e7-6084030a0db5'
    AND telefone   = '5581988280629'
    AND conteudo   = 'GRUPO_STATE:2b356352-0de2-4192-a7e7-72e37924de15:ATIVO';
  ```
- [ ] Confirmar que próxima notif/aquec da Karla cai no grupo (não DM 1-1)
- [ ] Phase 5 vai substituir esse SQL manual pelo endpoint admin

### Task 8: Atualizar memória
- [ ] Criar `.claude/projects/c--Projetos-Leadflow/memory/sessao_2026-05-20_grupo_lid_arquitetura.md` com:
  - Causa-raiz unificada @lid
  - Arquitetura: webhook captura + helper + 7 callers threadeados
  - Casos resolvidos (Karla) + casos pendentes pra Fases 4-9
  - NÃO reverter
- [ ] Adicionar pointer em MEMORY.md

## Success criteria

1. ✅ Build Easypanel sem erros nos primeiros 5min
2. ✅ Logs `[VERIFY-LEAD]` mostram `lid='<valor>'` quando lead_lid foi fornecido
3. ✅ Logs `[WEBHOOK-GRUPO]` mostram `LEAD_LID salvo` em entrada nova de lead
4. ✅ Lead novo entra com @lid → FSM=ATIVO no Supabase
5. ✅ Karla: aquec/notif #N+1 vão pro grupo (não DM)
6. ✅ Nenhum lead em ATIVO regrediu pra FALLBACK_1_1 nas próximas 24h (probe legacy funciona)

## Rollback plan

Se algo der errado em prod:
```bash
cd c:/Projetos/Leadflow/leadflow-backend
git revert <commit_hash>
git push
# Redeploy Easypanel
```

Risco baixo: fix é puramente aditivo (novo parâmetro com default `""`), não altera comportamento de callers que não passam `lead_lid`. Fallback semântico mantém regra atual.

## Dependencies

- Acesso ao Supabase Editor (user tem)
- Acesso ao painel Easypanel (user tem)
- Acesso ao git push (user tem)

## Next phase

Após smoke test OK → `/gsd-plan-phase 4` (Captura via MESSAGES_UPSERT).

---

*Created: 2026-05-20*
