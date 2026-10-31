const questionInput = document.getElementById('question');
const askBtn = document.getElementById('askBtn');
const answerText = document.getElementById('answerText');
const intentBadge = document.getElementById('intentBadge');
const generatedSql = document.getElementById('generatedSql');
const sqlBox = document.getElementById('sqlBox');
const viewSqlBtn = document.getElementById('viewSqlBtn');
const statBlock = document.getElementById('statBlock');
const statValue = document.getElementById('statValue');
const findingTitle = document.getElementById('findingTitle');
const methodText = document.getElementById('methodText');
const sourceText = document.getElementById('sourceText');

async function askQuestion() {
  const question = questionInput.value.trim();

  if (!question) {
    answerText.textContent = 'Please enter a question.';
    return;
  }

  askBtn.disabled = true;
  askBtn.textContent = 'RESEARCHING...';
  answerText.textContent = 'Researching...';
  intentBadge.textContent = 'WORKING';
  sqlBox.classList.add('hidden');
  findingTitle.classList.add('fade-in-up');

  try {
    const response = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Request failed');
    }

    const intent = (data.intent || 'result').toLowerCase();
    intentBadge.textContent = intent.toUpperCase();

    if (intent === 'sql') {
      findingTitle.textContent = 'SQL — direct database result';
      methodText.textContent = 'SQL / Placement database';
      sourceText.textContent = 'Placements table';
      // If the answer is a single numeric value, present as a statistic
      const value = data.answer;
      const textBody = document.getElementById('textBody');
      if (typeof value === 'number' || (!isNaN(Number(value)) && String(value).trim() !== '')) {
        statBlock.classList.remove('hidden');
        textBody.classList.add('hidden');
        // animated count
        animateNumber(statValue, Number(value));
      } else {
        statBlock.classList.add('hidden');
        textBody.classList.remove('hidden');
        answerText.textContent = data.answer || 'No result returned.';
      }
      if (data.generated_sql) {
        generatedSql.textContent = data.generated_sql;
        sqlBox.classList.remove('hidden');
      } else {
        sqlBox.classList.add('hidden');
      }
    } else {
      findingTitle.textContent = 'RAG — contextual answer';
      methodText.textContent = 'RAG / Document retrieval';
      sourceText.textContent = (data.sources || []).join(', ') || 'No sources';
      // show textual result
      const statBlock = document.getElementById('statBlock');
      statBlock.classList.add('hidden');
      document.getElementById('textBody').classList.remove('hidden');
      answerText.textContent = data.answer || 'No contextual answer returned.';
      sqlBox.classList.add('hidden');
    }

    // ensure entrance animation
    const blk = document.getElementById('answerBlock');
    blk.classList.add('fade-up');
    setTimeout(() => blk.classList.add('visible'), 20);
  } catch (error) {
    answerText.textContent = 'RESEARCH INTERRUPTED — please try again.';
    intentBadge.textContent = 'ERROR';
    console.error(error);
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = 'ASK →';
  }
}

askBtn.addEventListener('click', askQuestion);
questionInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    askQuestion();
  }
});

// Accessibility: focus-visible outline polyfill for keyboard users
document.addEventListener('keydown', (e) => {
  if (e.key === 'Tab') document.body.classList.add('user-is-tabbing');
});

// SQL toggle
if (viewSqlBtn) {
  viewSqlBtn.addEventListener('click', () => {
    if (sqlBox.classList.contains('hidden')) {
      sqlBox.classList.remove('hidden');
      viewSqlBtn.textContent = 'HIDE SQL';
    } else {
      sqlBox.classList.add('hidden');
      viewSqlBtn.textContent = 'VIEW GENERATED SQL →';
    }
  });
}

// simple animated number counter
function animateNumber(el, to) {
  if (!el) return;
  const start = Number(el.textContent.replace(/[^0-9.-]/g, '')) || 0;
  const duration = 800;
  const startTime = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - startTime) / duration);
    const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; // easeInOut quad
    const value = Math.round(start + (to - start) * eased);
    el.textContent = value.toLocaleString();
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
