"""
Testes da política de retenção das gravações locais.

Rodar::

    python -m unittest discover -s tests -v

Sem dependências externas (só stdlib), porque o projeto não tem infraestrutura
de testes e a política é pequena demais para justificar uma.

A regra central testada aqui é a de segurança: **MP3 sem upload confirmado
nunca é removido**, porque é a única cópia daquele áudio.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plaud_linux import retention  # noqa: E402


class BaseRetention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        # não herdar configuração do ambiente do usuário
        self._env = os.environ.pop(retention.RETENTION_ENV, None)
        # nem o ~/.plaud-linux/retention.conf da máquina de quem roda os testes
        self._conf = retention.CONFIG_PATH
        retention.CONFIG_PATH = os.path.join(self.dir, "inexistente.conf")
        self.addCleanup(self._restaura_config)
        self.addCleanup(self._restaura_env)

    def _restaura_env(self):
        if self._env is not None:
            os.environ[retention.RETENTION_ENV] = self._env

    def _restaura_config(self):
        retention.CONFIG_PATH = self._conf

    def mp3(self, nome, horas_atras=0.0, conteudo=b"x" * 100):
        """Cria um MP3 falso com mtime controlado."""
        caminho = os.path.join(self.dir, nome)
        with open(caminho, "wb") as fh:
            fh.write(conteudo)
        if horas_atras:
            quando = datetime.now().timestamp() - horas_atras * 3600
            os.utime(caminho, (quando, quando))
        return caminho

    def envelhece(self, caminho, dias):
        """Recua o mtime do arquivo em ``dias`` (0 = agora)."""
        quando = datetime.now().timestamp() - dias * 86400
        os.utime(caminho, (quando, quando))
        return caminho

    def marca(self, caminho, dias_atras=0.0):
        """Registra upload confirmado e alinha o mtime ao momento do upload.

        Na vida real o MP3 é gravado e enviado no mesmo instante, então o mtime
        fica junto do registro. Modelar isso é o que permite testar a detecção
        de arquivo alterado depois do upload (ver
        ``test_preserva_arquivo_modificado_depois_do_upload``).
        """
        quando = datetime.now(timezone.utc) - timedelta(days=dias_atras)
        self.assertTrue(retention.mark_uploaded(self.dir, caminho, quando=quando))
        instante = quando.timestamp()
        os.utime(caminho, (instante, instante))

    def existentes(self):
        return sorted(n for n in os.listdir(self.dir) if n.endswith(".mp3"))


class TestRetencaoPadrao(BaseRetention):
    def test_padrao_e_sete_dias(self):
        self.assertEqual(retention.get_retention_days(), 7)

    def test_env_sobrescreve(self):
        os.environ[retention.RETENTION_ENV] = "3"
        self.assertEqual(retention.get_retention_days(), 3)

    def test_zero_desativa(self):
        os.environ[retention.RETENTION_ENV] = "0"
        self.assertIsNone(retention.get_retention_days())

    def test_negativo_desativa(self):
        os.environ[retention.RETENTION_ENV] = "-2"
        self.assertIsNone(retention.get_retention_days())

    def test_valor_invalido_cai_no_padrao(self):
        os.environ[retention.RETENTION_ENV] = "sete"
        self.assertEqual(retention.get_retention_days(), 7)


class TestRemocao(BaseRetention):
    def test_remove_enviado_ha_mais_de_7_dias(self):
        f = self.mp3("plaud_2026-09-01_10-00-00.mp3")
        self.marca(f, dias_atras=8)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, ["plaud_2026-09-01_10-00-00.mp3"])
        self.assertEqual(self.existentes(), [])

    def test_preserva_enviado_ha_menos_de_7_dias(self):
        f = self.mp3("recente.mp3")
        self.marca(f, dias_atras=3)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertEqual(self.existentes(), ["recente.mp3"])
        self.assertEqual(r.dentro_do_prazo, 1)

    def test_limite_de_7_dias_exatos(self):
        f = self.mp3("na_borda.mp3")
        # 7 dias + 1 minuto -> já expirou
        self.marca(f, dias_atras=7 + 1 / 1440)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(len(r.removidos), 1)

    def test_dry_run_nao_remove(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=30)
        r = retention.prune(self.dir, dry_run=True, verboso=False)
        self.assertEqual(len(r.removidos), 1)
        self.assertTrue(os.path.exists(f), "dry-run não pode apagar")
        self.assertGreater(r.bytes_liberados, 0)

    def test_dias_customizados(self):
        f = self.mp3("ontem.mp3")
        self.marca(f, dias_atras=1)
        self.assertEqual(retention.prune(self.dir, dias=3, verboso=False).removidos, [])
        self.assertEqual(len(retention.prune(self.dir, dias=1, verboso=False).removidos), 1)

    def test_relata_bytes_liberados(self):
        f = self.mp3("grande.mp3", conteudo=b"y" * 5000)
        self.marca(f, dias_atras=10)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.bytes_liberados, 5000)


class TestSeguranca(BaseRetention):
    """O que NUNCA pode ser removido."""

    def test_nunca_remove_sem_registro_de_upload(self):
        self.mp3("orfao.mp3")          # upload nunca confirmado
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertEqual(self.existentes(), ["orfao.mp3"])
        self.assertEqual(r.sem_registro, 1)

    def test_nao_remove_se_registro_estiver_corrompido(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=30)
        with open(os.path.join(self.dir, retention.STATE_FILENAME), "w") as fh:
            fh.write("{ isso não é json")
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [], "registro ilegível não pode autorizar remoção")
        self.assertTrue(os.path.exists(f))

    def test_nao_confirma_upload_com_registro_corrompido(self):
        with open(os.path.join(self.dir, retention.STATE_FILENAME), "w") as fh:
            fh.write("corrompido")
        f = self.mp3("x.mp3")
        self.assertFalse(retention.mark_uploaded(self.dir, f))

    def test_preserva_arquivo_modificado_depois_do_upload(self):
        f = self.mp3("regravado.mp3")
        self.marca(f, dias_atras=10)
        os.utime(f, (datetime.now().timestamp(), datetime.now().timestamp()))
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertEqual(r.alterados_pos_upload, 1)

    def test_ignora_registro_de_arquivo_inexistente(self):
        self.assertEqual(retention.prune(self.dir, verboso=False).removidos, [])

    def test_ignora_nao_mp3(self):
        aberto = os.path.join(self.dir, "notas.txt")
        with open(aberto, "w") as fh:
            fh.write("nada")
        self.marca(aberto, dias_atras=30)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertTrue(os.path.exists(aberto))

    def test_nao_remove_gravacao_em_curso_wav(self):
        for nome in ("2026-09-18_10-00-00_mic.wav", "2026-09-18_10-00-00_system.wav"):
            with open(os.path.join(self.dir, nome), "wb") as fh:
                fh.write(b"w" * 50)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertEqual(len(os.listdir(self.dir)), 2)

    def test_retencao_desativada_nao_remove(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=99)
        os.environ[retention.RETENTION_ENV] = "0"
        r = retention.prune(self.dir, verboso=False)
        self.assertIsNone(r.dias)
        self.assertTrue(r.desativada)
        self.assertEqual(r.removidos, [])
        self.assertTrue(os.path.exists(f))


class TestRegistro(BaseRetention):
    def test_mark_uploaded_grava_iso(self):
        f = self.mp3("a.mp3")
        self.marca(f)
        dados = retention.load_uploaded(self.dir)
        self.assertIn("a.mp3", dados)
        datetime.fromisoformat(dados["a.mp3"])  # não pode explodir

    def test_idempotente(self):
        f = self.mp3("a.mp3")
        self.marca(f, dias_atras=2)
        self.marca(f, dias_atras=2)
        self.assertEqual(len(retention.load_uploaded(self.dir)), 1)

    def test_registro_limpo_apos_remocao(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=30)
        retention.prune(self.dir, verboso=False)
        self.assertEqual(retention.load_uploaded(self.dir), {})

    def test_preserva_registro_dos_que_ficam(self):
        velho = self.mp3("velho.mp3")
        novo = self.mp3("novo.mp3")
        self.marca(velho, dias_atras=30)
        self.marca(novo, dias_atras=1)
        retention.prune(self.dir, verboso=False)
        self.assertEqual(list(retention.load_uploaded(self.dir)), ["novo.mp3"])

    def test_aceita_sufixo_z(self):
        f = self.mp3("z.mp3")
        with open(os.path.join(self.dir, retention.STATE_FILENAME), "w") as fh:
            json.dump({"z.mp3": "2020-01-01T00:00:00Z"}, fh)
        # o mtime precisa acompanhar o upload, senão o arquivo parece ter sido
        # modificado depois dele e é preservado (comportamento correto)
        antigo = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(f, (antigo, antigo))
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, ["z.mp3"])

    def test_find_expired_nao_remove(self):
        f = self.mp3("velho.mp3")
        self.marca(f, dias_atras=30)
        expirados = retention.find_expired(self.dir, 7)
        self.assertEqual(len(expirados), 1)
        self.assertTrue(os.path.exists(f), "find_expired é somente leitura")

    def test_registro_temporario_nao_fica_para_tras(self):
        f = self.mp3("a.mp3")
        self.marca(f)
        self.assertFalse(os.path.exists(os.path.join(self.dir, retention.STATE_FILENAME + ".tmp")))


class TestConfig(BaseRetention):
    """``~/.plaud-linux/retention.conf`` — a configuração durável do usuário."""

    def escreve_conf(self, texto):
        caminho = os.path.join(self.dir, "retention.conf")
        with open(caminho, "w", encoding="utf-8") as fh:
            fh.write(texto)
        return caminho

    def test_arquivo_ausente_usa_padrao(self):
        self.assertEqual(retention.get_retention_days(), retention.DEFAULT_RETENTION_DAYS)

    def test_le_days(self):
        conf = self.escreve_conf("days=30\n")
        self.assertEqual(retention.get_retention_days(conf), 30)

    def test_ignora_comentarios_e_linhas_vazias(self):
        conf = self.escreve_conf("# comentario\ndays = 3\n\n")
        self.assertEqual(retention.get_retention_days(conf), 3)

    def test_comentario_na_mesma_linha(self):
        conf = self.escreve_conf("days=14  # duas semanas\n")
        self.assertEqual(retention.get_retention_days(conf), 14)

    def test_days_ausente_cai_para_env(self):
        conf = self.escreve_conf("outra_coisa=1\n")
        os.environ[retention.RETENTION_ENV] = "21"
        self.assertEqual(retention.get_retention_days(conf), 21)

    def test_config_tem_precedencia_sobre_env(self):
        conf = self.escreve_conf("days=1\n")
        os.environ[retention.RETENTION_ENV] = "99"
        self.assertEqual(retention.get_retention_days(conf), 1)

    def test_valor_invalido_nao_usa_env(self):
        """Config existe e é inválido: cai no padrão, não no env."""
        conf = self.escreve_conf("days=abc\n")
        os.environ[retention.RETENTION_ENV] = "99"
        self.assertEqual(retention.get_retention_days(conf),
                         retention.DEFAULT_RETENTION_DAYS)

    def test_valor_invalido_nao_apaga_tudo(self):
        """``days=abc`` não pode virar 0 e apagar o histórico."""
        conf = self.escreve_conf("days=abc\n")
        self.assertEqual(retention.get_retention_days(conf), retention.DEFAULT_RETENTION_DAYS)

    def test_zero_desativa(self):
        conf = self.escreve_conf("days=0\n")
        self.assertIsNone(retention.get_retention_days(conf))

    def test_negativo_desativa(self):
        conf = self.escreve_conf("days=-5\n")
        self.assertIsNone(retention.get_retention_days(conf))

    def test_conf_define_o_comportamento_do_prune(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=10)
        retention.CONFIG_PATH = self.escreve_conf("days=30\n")
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.dias, 30)
        self.assertTrue(os.path.exists(f), "10 dias atrás está dentro de 30")

    def test_conf_invalido_nao_acelera_a_limpeza(self):
        f = self.mp3("novo.mp3")
        self.marca(f, dias_atras=1)
        retention.CONFIG_PATH = self.escreve_conf("days=lixo\n")
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.dias, retention.DEFAULT_RETENTION_DAYS)
        self.assertTrue(os.path.exists(f))


class TestAdocao(BaseRetention):
    """MP3 anteriores à política não têm registro — e por isso nunca sairiam."""

    def test_historico_sem_registro_nunca_e_removido(self):
        f = self.envelhece(self.mp3("historico.mp3"), 90)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertTrue(os.path.exists(f))
        self.assertEqual(r.sem_registro, 1)

    def test_adopt_marca_e_libera_a_retencao(self):
        self.envelhece(self.mp3("historico.mp3"), 90)
        self.assertEqual(retention.adopt_existing(self.dir, verboso=False), 1)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, ["historico.mp3"])

    def test_adopt_nao_toca_arquivo_recente(self):
        f = self.mp3("recente.mp3")
        retention.adopt_existing(self.dir, verboso=False)
        r = retention.prune(self.dir, verboso=False)
        self.assertEqual(r.removidos, [])
        self.assertTrue(os.path.exists(f))

    def test_adopt_dry_run_nao_grava(self):
        self.mp3("historico.mp3")
        self.assertEqual(
            retention.adopt_existing(self.dir, dry_run=True, verboso=False), 1)
        self.assertEqual(retention.load_uploaded(self.dir), {})

    def test_adopt_e_idempotente(self):
        self.mp3("a.mp3")
        retention.adopt_existing(self.dir, verboso=False)
        primeiro = retention.load_uploaded(self.dir)
        self.assertEqual(retention.adopt_existing(self.dir, verboso=False), 0)
        self.assertEqual(retention.load_uploaded(self.dir), primeiro)

    def test_adopt_preserva_registro_existente(self):
        novo = self.mp3("novo.mp3")
        self.marca(novo, dias_atras=1)
        antes = retention.load_uploaded(self.dir)["novo.mp3"]
        self.mp3("historico.mp3")
        retention.adopt_existing(self.dir, verboso=False)
        self.assertEqual(retention.load_uploaded(self.dir)["novo.mp3"], antes)

    def test_adopt_nao_toca_wav(self):
        wav = os.path.join(self.dir, "2026-01-01_mic.wav")
        with open(wav, "wb") as fh:
            fh.write(b"w" * 10)
        retention.adopt_existing(self.dir, verboso=False)
        self.assertEqual(retention.load_uploaded(self.dir), {})
        self.assertTrue(os.path.exists(wav))

    def test_adopt_com_registro_corrompido_nao_faz_nada(self):
        f = self.mp3("a.mp3")
        with open(os.path.join(self.dir, retention.STATE_FILENAME), "w") as fh:
            fh.write("{lixo")
        self.assertEqual(retention.adopt_existing(self.dir, verboso=False), 0)
        self.assertEqual(retention.load_uploaded(self.dir), {})
        self.assertTrue(os.path.exists(f))

    def test_cli_adopt_existing(self):
        self.envelhece(self.mp3("historico.mp3"), 90)
        self.assertEqual(
            retention.main(["--dir", self.dir, "--adopt-existing"]), 0)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "historico.mp3")))


class TestCLI(BaseRetention):
    def test_cli_dry_run(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=30)
        self.assertEqual(retention.main(["--dir", self.dir, "--dry-run"]), 0)
        self.assertTrue(os.path.exists(f))

    def test_cli_remove(self):
        f = self.mp3("antigo.mp3")
        self.marca(f, dias_atras=30)
        self.assertEqual(retention.main(["--dir", self.dir, "--days", "7"]), 0)
        self.assertFalse(os.path.exists(f))

    def test_cli_dir_inexistente_nao_quebra(self):
        self.assertEqual(retention.main(["--dir", os.path.join(self.dir, "nao_existe")]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
