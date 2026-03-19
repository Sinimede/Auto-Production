# Test Day Protocol

**Data:** 2026-03-17
**Objetivo:** Validar todas as features contra SolidWorks real. Registar PASS/FAIL e notas.

---

## 0. Sanity Check (antes de abrir o SolidWorks)

```bash
cd "c:/Users/Micael/Desktop/Auto Production/tools/exporter"
python -m pytest tests/ -v
```

**Critério:** 156 passed, exatamente 5 falhanços em `TestBomTraverse` (pré-existentes). Qualquer outro falhanço é STOP — investigar antes de continuar.

- [ ] PASS / [ ] FAIL — notas:

---

## 1. Setup

1. Abrir SolidWorks
2. Carregar montagem de teste (assembly com sub-assemblies aninhados)
3. Lançar `dist\AutoProduction\AutoProduction.exe`

- [ ] Executável abre sem erros
- [ ] GUI carrega corretamente

---

## 🟡 Bug — Traversal de Assemblies Aninhados — FIX IMPLEMENTADO, falta validar com SW

**Causa raiz identificada (sessão 2026-03-17):**
`IsSuppressed` em SW 2024 retorna `True` para componentes **lightweight** (não completamente carregados), que aparecem como ativos no Feature Tree. O BOM saltava estes componentes incorretamente.

**Fix aplicado:** `_bom_traverse` em `solidworks.py` — substituído `IsSuppressed` por `GetSuppression() == 0` (só skip se verdadeiramente suprimido, state=0).

**Testes:** 162/162 passam (7 TestBomTraverse agora incluídos, antes eram 5 falhanços pré-existentes).

**Falta validar com SW real:**
1. Abrir SW + montagem 15024 Pack and Go conj 100 (171 peças únicas não suprimidas)
2. Lançar `dist\AutoProduction\AutoProduction.exe`
3. Gerar BOM → verificar que aparece próximo de 171 peças únicas (produção + comercial)
4. Confirmar que quantidades estão corretas

- [x] Fix implementado e testado unitariamente
- [ ] Validado com SW real

---

## 2. DXF Laser

**Setup:** Selecionar processo "Laser" no painel DXF.

### 2a. Export normal
1. Selecionar montagem com peças `LASER` e `LASER+QUINAGEM`
2. Exportar DXFs
3. Verificar que os ficheiros gerados existem e abrem corretamente

- [ ] PASS / [ ] FAIL — notas:

### 2b. Exclusão de Soldadura *(nova funcionalidade)*
1. Confirmar que existem peças com `LASER+QUINAGEM+SOLDADURA` na montagem
2. Correr export DXF Laser
3. **Critério:** essas peças NÃO devem aparecer na lista nem gerar ficheiro DXF

- [ ] PASS / [ ] FAIL — notas:

### 2c. Peça sem propriedade Corte_Fabrico
1. Testar com peça que não tem a propriedade definida
2. **Critério:** não crasha, simplesmente ignora a peça

- [ ] PASS / [ ] FAIL — notas:

---

## 3. DXF Proteções

1. Selecionar processo "Proteções" no painel DXF
2. Exportar DXFs de peças com `PROTEÇÕES` / `Proteções` / `PROTEÇÕES+QUINAGEM`
3. Verificar ficheiros gerados

- [ ] PASS / [ ] FAIL — notas:

---

## 4. STEP Exporter

1. Selecionar componentes no painel STEP
2. Exportar
3. Verificar que ficheiros `.STEP` gerados abrem no SolidWorks ou visualizador

- [ ] PASS / [ ] FAIL — notas:

---

## 5. Lista de Material (BOM)

1. Gerar BOM da montagem
2. Verificar: todas as peças presentes, quantidades corretas, propriedades corretas (material, descrição, etc.)
3. Cruzar com Feature Tree do SolidWorks manualmente para 5-10 peças

- [ ] PASS / [ ] FAIL — notas:
- Peças em falta (se houver):

---

## 6. Listas — Perfis de Alumínio

1. Gerar lista de perfis
2. Verificar deteção de pontas tapadas (peças com caps)
3. Verificar comprimentos

- [ ] PASS / [ ] FAIL — notas:

---

## 7. Gerar Tudo

1. Correr "Gerar Tudo" (DXF + STEP + BOM em sequência)
2. Verificar que cria pasta única com todos os outputs
3. **Teste de falha parcial:** simular erro num passo (ex: ficheiro bloqueado) — os outros passos devem continuar

- [ ] PASS / [ ] FAIL — notas:
- Pasta criada:
- Falha parcial comporta-se corretamente: [ ] Sim / [ ] Não

---

## Resumo do Dia

| Feature | Status | Notas |
|---|---|---|
| Traversal aninhado (bug) | | |
| DXF Laser | | |
| DXF Laser — exclusão soldadura | | |
| DXF Proteções | | |
| STEP | | |
| BOM | | |
| Listas / Perfis | | |
| Gerar Tudo | | |

**Bugs encontrados:**

1.
2.
3.
