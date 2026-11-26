document.addEventListener("DOMContentLoaded", () => {

    const container = document.getElementById("chat-container");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const messages = document.getElementById("chat-messages");
    const sendButton = document.getElementById("chat-send");
    const newChat = document.getElementById("nova-conversa");

    // Executar somente na página do assistente
    if (!container || !form) return;

    let historico = [];
    let aguardando = false;

    const conteudoInicial = messages.innerHTML;

    function rolarChat() {
        messages.scrollTop = messages.scrollHeight;
    }

    function adicionarMensagem(texto, papel) {

        const mensagem = document.createElement("div");

        mensagem.className = "chat-message " + papel;

        if (papel === "assistant") {

            const avatar = document.createElement("div");

            avatar.className = "message-avatar";
            avatar.innerHTML = '<i class="bi bi-stars"></i>';

            mensagem.appendChild(avatar);
        }

        const conteudo = document.createElement("div");

        conteudo.className = "message-content";
        conteudo.textContent = texto;

        mensagem.appendChild(conteudo);

        messages.appendChild(mensagem);

        rolarChat();

        return mensagem;
    }

    async function enviarMensagem(pergunta) {

        pergunta = pergunta.trim();

        if (!pergunta || aguardando) return;

        aguardando = true;

        input.disabled = true;
        sendButton.disabled = true;
        newChat.disabled = true;

        const sugestoes = document.getElementById(
            "chat-suggestions"
        );

        if (sugestoes) sugestoes.remove();

        adicionarMensagem(pergunta, "user");

        input.value = "";

        const carregando = adicionarMensagem(
            "Analisando as informações...",
            "assistant"
        );

        carregando.classList.add("loading-message");

        try {

            const resposta = await fetch(
                container.dataset.endpoint,
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        pergunta: pergunta,
                        historico: historico.slice(-6)
                    })
                }
            );

            const dados = await resposta.json();

            if (!resposta.ok) {

                throw new Error(
                    dados.erro || "Erro na comunicação."
                );
            }

            carregando.remove();

            adicionarMensagem(
                dados.resposta,
                "assistant"
            );

            historico.push({
                papel: "usuario",
                texto: pergunta
            });

            historico.push({
                papel: "assistente",
                texto: dados.resposta
            });

            historico = historico.slice(-6);

        } catch (erro) {

            carregando.remove();

            adicionarMensagem(
                "Não foi possível obter uma resposta. " +
                "Tente novamente.",
                "assistant"
            );

        } finally {

            aguardando = false;

            input.disabled = false;
            sendButton.disabled = false;
            newChat.disabled = false;

            input.focus();

            rolarChat();
        }
    }

    // Envio pelo formulário
    form.addEventListener("submit", (evento) => {

        evento.preventDefault();

        enviarMensagem(input.value);
    });

    // Enter envia; Shift + Enter quebra a linha
    input.addEventListener("keydown", (evento) => {

        if (
            evento.key === "Enter"
            && !evento.shiftKey
            && !evento.isComposing
        ) {

            evento.preventDefault();

            enviarMensagem(input.value);
        }
    });

    // Perguntas sugeridas
    messages.addEventListener("click", (evento) => {

        const sugestao = evento.target.closest(".suggestion");

        if (sugestao) {

            enviarMensagem(sugestao.textContent.trim());
        }
    });

    // Reiniciar a conversa
    newChat.addEventListener("click", () => {

        if (aguardando) return;

        historico = [];

        messages.innerHTML = conteudoInicial;

        input.value = "";

        input.focus();

        messages.scrollTop = 0;
    });

});
