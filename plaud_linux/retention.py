"""
Retenção das gravações locais.

O diretório ``~/.plaud-linux/recordings/`` guarda cada MP3 gravado para sempre,
inclusive depois do upload para a nuvem ter dado certo — cerca de 100 MB por
hora de gravação acumulando sem limite no disco.

Esta política remove os MP3 **já enviados com sucesso** depois de N dias
(padrão: 7). A regra que não pode ser quebrada: um MP3 cujo upload falhou — ou
que nunca foi tentado — é a **única cópia** daquele áudio e nunca é removido
automaticamente. Sem registro de upload confirmado, o arquivo fica.

Configuração
------------

``~/.plaud-linux/retention.conf``
    Arquivo opcional com ``days=N``. É a configuração durável e tem precedência
    sobre a variável de ambiente::

        days=7

``PLAUD_RETENTION_DAYS``
    Dias de retenção dos MP3 já enviados. Padrão ``7``. ``0`` ou negativo
    desativa a limpeza (comportamento antigo: guarda tudo para sempre).

Uso programático::

    from plaud_linux.retention import mark_uploaded, prune

    if uploader.upload(mp3_path):
        mark_uploaded(recordings_dir, mp3_path)

    prune(recordings_dir)

Ou pela linha de comando, útil para cron::

    plaud-linux-prune --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

#: Dias de retenção padrão para MP3 já enviados.
DEFAULT_RETENTION_DAYS = 7

#: Variável de ambiente que sobrescreve a retenção.
RETENTION_ENV = "PLAUD_RETENTION_DAYS"

#: Arquivo de configuração (opcional), ao lado do estado do app.
CONFIG_PATH = os.path.expanduser("~/.plaud-linux/retention.conf")

#: Arquivo (escondido, dentro de recordings/) que registra os uploads confirmados.
STATE_FILENAME = ".uploaded.json"


@dataclass
class PruneResult:
    """O que a limpeza fez — e o que ela deliberadamente preservou."""

    dias: int | None
    removidos: list[str] = field(default_factory=list)
    bytes_liberados: int = 0
    dentro_do_prazo: int = 0
    sem_registro: int = 0
    alterados_pos_upload: int = 0

    @property
    def desativada(self) -> bool:
        return self.dias is None


def _dias_do_config(caminho: str | None = None) -> tuple[bool, int | None]:
    """Lê ``days=`` de ``~/.plaud-linux/retention.conf``.

    Devolve ``(encontrado, valor)``. ``encontrado=False`` significa "arquivo ou
    chave ausente" — aí o chamador ainda pode consultar a variável de ambiente.
    ``(True, None)`` significa "a chave existe mas o valor é inválido": o
    chamador deve usar o **padrão**, nunca cair para outra fonte, para que um
    ``days=lixo`` não mude silenciosamente por quanto tempo os áudios vivem.
    """
    caminho = caminho or CONFIG_PATH
    try:
        with open(caminho, encoding="utf-8") as fh:
            linhas = fh.readlines()
    except FileNotFoundError:
        return (False, None)
    except (OSError, UnicodeDecodeError) as erro:
        print(f"⚠️  Não foi possível ler {caminho} ({erro}); "
              f"usando o padrão de {DEFAULT_RETENTION_DAYS} dias.")
        return (True, None)

    for linha in linhas:
        texto = linha.split("#", 1)[0].strip()
        if not texto or "=" not in texto:
            continue
        chave, _, valor = texto.partition("=")
        if chave.strip().lower() != "days":
            continue
        try:
            return (True, int(valor.strip()))
        except ValueError:
            print(f"⚠️  days={valor.strip()!r} em {caminho} não é um inteiro; "
                  f"usando o padrão de {DEFAULT_RETENTION_DAYS} dias.")
            return (True, None)
    return (False, None)


def get_retention_days(config_path: str | None = None) -> int | None:
    """Retenção efetiva em dias, ou ``None`` quando a limpeza está desativada.

    Precedência: ``retention.conf`` > ``PLAUD_RETENTION_DAYS`` > padrão (7).
    O arquivo vem primeiro porque é a configuração durável do usuário; a
    variável de ambiente serve para um ajuste pontual. Valor inválido no arquivo
    cai no padrão — não na variável — para que um erro de digitação nunca altere
    o prazo de remoção por conta própria.
    """
    achou, dias = _dias_do_config(config_path)
    if not achou:
        bruto = os.environ.get(RETENTION_ENV)
        if bruto is not None and bruto.strip():
            try:
                dias = int(bruto.strip())
            except ValueError:
                print(
                    f"⚠️  {RETENTION_ENV}={bruto!r} não é um inteiro; "
                    f"usando o padrão de {DEFAULT_RETENTION_DAYS} dias."
                )
                dias = DEFAULT_RETENTION_DAYS
        else:
            dias = DEFAULT_RETENTION_DAYS
    elif dias is None:
        dias = DEFAULT_RETENTION_DAYS
    # 0 ou negativo = guardar tudo (comportamento antigo)
    return None if dias <= 0 else dias


def _state_path(recordings_dir: str) -> str:
    return os.path.join(recordings_dir, STATE_FILENAME)


def _ler_registro(recordings_dir: str) -> dict | None:
    """Lê o registro de uploads. ``None`` significa ilegível (não confiável)."""
    try:
        with open(_state_path(recordings_dir), encoding="utf-8") as fh:
            dados = json.load(fh)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as erro:
        print(f"⚠️  Registro de uploads ilegível ({erro}); nada será removido.")
        return None
    return dados if isinstance(dados, dict) else None


def load_uploaded(recordings_dir: str) -> dict[str, str]:
    """Mapa ``nome_do_arquivo -> instante do upload confirmado`` (ISO 8601)."""
    return _ler_registro(recordings_dir) or {}


def _gravar_registro(recordings_dir: str, dados: dict) -> bool:
    """Grava o registro de forma atômica, para não corromper em queda."""
    caminho = _state_path(recordings_dir)
    temporario = f"{caminho}.tmp"
    try:
        os.makedirs(recordings_dir, exist_ok=True)
        with open(temporario, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, indent=1, ensure_ascii=False, sort_keys=True)
        os.replace(temporario, caminho)
        return True
    except OSError as erro:
        print(f"⚠️  Não foi possível gravar {caminho}: {erro}")
        try:
            os.remove(temporario)
        except OSError:
            pass
        return False


def mark_uploaded(recordings_dir: str, mp3_path: str,
                  quando: datetime | None = None) -> bool:
    """Registra que ``mp3_path`` foi confirmado na nuvem.

    Chamar **somente** depois de o upload ter dado certo: é este registro que
    autoriza a remoção futura. Sem ele, o arquivo é preservado indefinidamente.
    """
    estado = _ler_registro(recordings_dir)
    if estado is None:
        # Registro corrompido: não sobrescrever (perderia as outras entradas e
        # tornaria os arquivos impurgáveis). Nada é removido sem registro.
        return False
    instante = quando or datetime.now(timezone.utc)
    estado[os.path.basename(mp3_path)] = instante.isoformat()
    return _gravar_registro(recordings_dir, estado)


def _para_timestamp(valor: str) -> float | None:
    """Converte o ISO guardado no registro em epoch; ``None`` se ilegível."""
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    if texto.endswith(("Z", "z")):
        texto = texto[:-1] + "+00:00"
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.timestamp()


def find_expired(recordings_dir: str, dias: int,
                 agora: float | None = None) -> list[tuple[str, float]]:
    """MP3 já enviados que passaram do prazo. Não remove nada."""
    agora = time.time() if agora is None else agora
    limite = dias * 86400
    expirados: list[tuple[str, float]] = []
    for nome, quando in load_uploaded(recordings_dir).items():
        caminho = os.path.join(recordings_dir, nome)
        if not os.path.isfile(caminho):
            continue
        enviado_em = _para_timestamp(quando)
        if enviado_em is None:
            continue
        if agora - enviado_em >= limite:
            expirados.append((caminho, enviado_em))
    return sorted(expirados, key=lambda item: item[1])


def prune(recordings_dir: str, dias: int | None = None, dry_run: bool = False,
          agora: float | None = None, verboso: bool = True) -> PruneResult:
    """Remove MP3 já enviados com mais de ``dias``. Preserva o resto.

    Um MP3 só é removido quando as três condições valem:

    1. existe registro de upload confirmado para ele;
    2. o upload foi há ``dias`` ou mais;
    3. o arquivo não foi modificado depois do upload (senão não é o mesmo
       áudio que subiu, e sim uma regravação).
    """
    if dias is None:
        dias = get_retention_days()

    resultado = PruneResult(dias=dias)
    if dias is None:
        if verboso:
            print("ℹ️  Retenção desativada "
                  f"({RETENTION_ENV}=0) — gravações mantidas indefinidamente.")
        return resultado

    if not os.path.isdir(recordings_dir):
        return resultado

    agora = time.time() if agora is None else agora
    limite = dias * 86400
    registro = load_uploaded(recordings_dir)

    # Uma passada pelo disco: cada MP3 é classificado e, quando elegível,
    # removido. Classificar aqui (e não pelo registro) é o que faz o relatório
    # contar também os arquivos que nunca foram enviados.
    for mp3 in sorted(os.listdir(recordings_dir)):
        if mp3 == STATE_FILENAME or not mp3.lower().endswith(".mp3"):
            continue
        caminho = os.path.join(recordings_dir, mp3)
        if not os.path.isfile(caminho):
            continue

        enviado_em = _para_timestamp(registro.get(mp3, ""))
        if enviado_em is None:
            # Sem upload confirmado: única cópia daquele áudio -> preserva.
            resultado.sem_registro += 1
            continue
        if agora - enviado_em < limite:
            resultado.dentro_do_prazo += 1
            continue
        # Modificado depois do upload => o que está no disco não é o que subiu.
        if os.path.getmtime(caminho) > enviado_em + 1:
            resultado.alterados_pos_upload += 1
            continue

        try:
            tamanho = os.path.getsize(caminho)
            if not dry_run:
                os.remove(caminho)
            resultado.removidos.append(mp3)
            resultado.bytes_liberados += tamanho
        except OSError as erro:
            print(f"⚠️  Não foi possível remover {mp3}: {erro}")

    # Limpa registros de arquivos que já não existem.
    if not dry_run and resultado.removidos:
        sobraram = {n: q for n, q in registro.items()
                    if os.path.isfile(os.path.join(recordings_dir, n))}
        if sobraram != registro:
            _gravar_registro(recordings_dir, sobraram)

    if verboso:
        _relatar(resultado, recordings_dir, dry_run)
    return resultado


def _relatar(resultado: PruneResult, recordings_dir: str, dry_run: bool) -> None:
    if not resultado.removidos:
        print(f"🧹 Nada a limpar (retenção de {resultado.dias} dias). "
              f"{resultado.dentro_do_prazo} dentro do prazo, "
              f"{resultado.sem_registro} sem upload confirmado.")
        return

    acao = "seriam removidos" if dry_run else "removidos"
    for nome in resultado.removidos:
        print(f"   🗑️  {nome}")
    print(f"🧹 {len(resultado.removidos)} MP3 {acao} "
          f"({_humano(resultado.bytes_liberados)}), retenção de {resultado.dias} dias")
    if resultado.sem_registro:
        print(f"   ℹ️  {resultado.sem_registro} preservados por não ter upload confirmado")
    if resultado.alterados_pos_upload:
        print(f"   ℹ️  {resultado.alterados_pos_upload} preservados por terem sido "
              f"modificados depois do upload")


def _humano(bytes_: int) -> str:
    valor = float(bytes_)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            return f"{valor:.1f}{unidade}"
        valor /= 1024
    return f"{valor:.1f}TB"


def adopt_existing(recordings_dir: str, agora: float | None = None,
                   dry_run: bool = False, verboso: bool = True) -> int:
    """Marca MP3 já existentes (sem registro) como enviados, usando o mtime.

    Sem isso, um "histórico" que já estava no disco nunca é removido: o registro
    é a prova do upload e arquivos anteriores a esta política não têm nenhuma.
    Como o mtime não é prova de upload, isto é **opt-in** e existe para o caso em
    que o usuário sabe que aqueles áudios já estão na nuvem.

    Devolve quantos arquivos passaram a ser elegíveis. Com ``dry_run`` conta mas
    não grava.
    """
    if not os.path.isdir(recordings_dir):
        return 0
    agora = time.time() if agora is None else agora
    registro = _ler_registro(recordings_dir)
    if registro is None:
        # Registro ilegível: adotar aqui sobrescreveria o que já existe.
        print("⚠️  Registro de uploads ilegível; nada foi adotado.")
        return 0

    adotados = 0
    for mp3 in sorted(os.listdir(recordings_dir)):
        if mp3 == STATE_FILENAME or not mp3.lower().endswith(".mp3"):
            continue
        caminho = os.path.join(recordings_dir, mp3)
        if not os.path.isfile(caminho) or mp3 in registro:
            continue
        try:
            mtime = os.path.getmtime(caminho)
        except OSError:
            continue
        momento = datetime.fromtimestamp(min(mtime, agora), tz=timezone.utc)
        registro[mp3] = momento.isoformat()
        adotados += 1

    if not adotados:
        if verboso:
            print("📥 Nenhum MP3 sem registro para adotar.")
        return 0

    if dry_run:
        if verboso:
            print(f"📥 {adotados} MP3 existentes seriam marcados como enviados "
                  f"(data = mtime); nada foi gravado (--dry-run).")
        return adotados

    if not _gravar_registro(recordings_dir, registro):
        return 0
    if verboso:
        print(f"📥 {adotados} MP3 existentes marcados como enviados "
              f"(data = mtime do arquivo); agora ficam sujeitos à retenção.")
    return adotados


def mark_and_prune(recordings_dir: str, mp3_path: str, sucesso: bool) -> None:
    """Registra o upload confirmado e aplica a retenção.

    Só marca quando o upload realmente deu certo: o registro é o que autoriza a
    remoção futura, então um MP3 que falhou (ou nem foi tentado) continua sendo
    a única cópia daquele áudio e fica para sempre.
    """
    if not sucesso:
        return
    if mark_uploaded(recordings_dir, mp3_path):
        prune(recordings_dir)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``plaud-linux-prune`` — pensado para rodar em cron."""
    padrao = os.path.join(os.path.expanduser("~"), ".plaud-linux", "recordings")
    parser = argparse.ArgumentParser(
        prog="plaud-linux-prune",
        description="Remove gravações locais já enviadas para a nuvem após "
                    f"{DEFAULT_RETENTION_DAYS} dias (padrão). "
                    "MP3 sem upload confirmado nunca são removidos.",
    )
    parser.add_argument("--days", type=int, default=None,
                        help=f"dias de retenção (padrão: {DEFAULT_RETENTION_DAYS} "
                             f"ou {RETENTION_ENV})")
    parser.add_argument("--dir", default=padrao,
                        help=f"diretório de gravações (padrão: {padrao})")
    parser.add_argument("--dry-run", action="store_true",
                        help="só mostrar o que sairia, sem apagar")
    parser.add_argument("--adopt-existing", action="store_true",
                        help="marcar MP3 antigos (sem registro) como já enviados, "
                             "usando o mtime como data; sem isto eles nunca são "
                             "removidos, porque o registro é a prova do upload")
    args = parser.parse_args(argv)

    if args.adopt_existing:
        adopt_existing(args.dir, dry_run=args.dry_run, verboso=True)

    resultado = prune(args.dir, dias=args.days, dry_run=args.dry_run)
    # Sempre 0: para o cron, "nada a limpar" não é erro.
    return 0


if __name__ == "__main__":
    sys.exit(main())
