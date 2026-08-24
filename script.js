const askButton = document.getElementById("ask-button");
const questionInput = document.getElementById("question");
const answerBox = document.getElementById("answer-box");

askButton.addEventListener("click", async function () {
    const question = questionInput.value;

    if (question === "") {
        return;
    }

    answerBox.textContent = "Thinking...";

    try {
        const response = await fetch("http://127.0.0.1:8000/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ question: question })
        });

        const data = await response.json();

        answerBox.innerHTML = `
            <p>${data.answer}</p>
            <p><em>Sources: ${data.sources.join(", ")}</em></p>
        `;  

    } catch (error) {
        answerBox.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});