"""Testes locais: não usam o banco original nem a API Gemini."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import banco


class AuditRegTest(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(banco, 'CAMINHO_BANCO', Path(pasta) / 'teste.db'))
        for criar in (banco.criar_tabelas_fontes, banco.criar_tabela_pendencias,
                      banco.criar_tabela_historico, banco.criar_tabela_retificacoes,
                      banco.criar_tabela_edicoes, banco.criar_tabela_exclusoes):
            criar()

    def comparar(self, codigo):
        return banco.comparar_registros(**banco.consultar_registro(codigo))

    def test_geracao_capacidade(self):
        codigos = banco.gerar_registros(3, 'misto')
        self.assertEqual(len(codigos), 3)
        self.assertEqual(banco.obter_capacidade()['total'], 3)
        self.assertEqual(len({self.comparar(c)['situacao'] for c in codigos}), 3)
        banco.gerar_registros(20, 'correto')
        banco.gerar_registros(20, 'correto')
        banco.gerar_registros(7, 'correto')
        with self.assertRaises(ValueError):
            banco.gerar_registros(1, 'correto')

    def test_retificacao_historico(self):
        codigo = banco.gerar_registros(1, 'divergente')[0]
        original = self.comparar(codigo)
        identificador = banco.registrar_auditoria(codigo, original, 'Teste')
        pendencia = banco.listar_pendencias()[0]
        valores = banco.obter_dados_retificacao(pendencia)
        args = (pendencia['id'], 'principal', str(valores['secundario']), 'Conferido',
                str(valores['principal']), str(valores['secundario']))
        self.assertFalse(banco.atualizar_pendencia(pendencia['id'], 'Resolvida', 'Teste'))
        self.assertFalse(banco.retificar_registro(*args[:-2], 'desatualizado', args[-1]))
        self.assertTrue(banco.retificar_registro(*args))
        self.assertFalse(self.comparar(codigo)['divergencias'])
        self.assertEqual(banco.consultar_auditoria(identificador)['divergencias'], original['divergencias'])
        self.assertEqual(len(banco.listar_retificacoes()), 1)
        self.assertEqual(banco.listar_pendencias()[0]['status'], 'Resolvida')
        banco.excluir_cadastro(codigo, 'ambas')
        self.assertIsNotNone(banco.consultar_auditoria(identificador))
        self.assertNotEqual(banco.gerar_registros(1, 'correto')[0], codigo)

    def test_edicao(self):
        codigo = banco.gerar_registros(1, 'correto')[0]
        dados = banco.consultar_registro(codigo)['principal']
        dados['status'] = 'Pendente'
        self.assertTrue(banco.editar_cadastro(codigo, 'principal', dados))
        self.assertIn('status', self.comparar(codigo)['divergencias'])
        self.assertTrue(banco.obter_contexto_assistente()['pendencias'])


if __name__ == '__main__':
    unittest.main()
