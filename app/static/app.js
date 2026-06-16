const state = {
    authenticated: false,
    clients: [],
    cars: [],
    works: [],
    parts: [],
    mechanics: [],
    orders: [],
    selectedOrderId: null,
    ops: {
        activeTab: 'radar',
        radar: [],
        radarDescription: '',
        priority: [],
        stuck: [],
        maintenance: [],
    },
};

const statuses = [
    'открыт',
    'ожидание запчастей',
    'в работе',
    'выполнен',
    'закрыт',
    'отменен',
];

const money = (value) => new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
}).format(value || 0);

const api = async (url, options = {}) => {
    const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (response.status === 401 && url !== '/api/auth/login') {
        showLogin();
    }
    if (!response.ok) {
        throw new Error(data?.error || 'Ошибка запроса');
    }
    return data;
};

const showLogin = () => {
    state.authenticated = false;
    document.body.classList.add('locked');
};

const showApp = () => {
    state.authenticated = true;
    document.body.classList.remove('locked');
};

const toast = (message) => {
    const box = document.querySelector('#toast');
    box.textContent = message;
    box.classList.add('show');
    setTimeout(() => box.classList.remove('show'), 2600);
};

const asJson = (form) => {
    const data = Object.fromEntries(new FormData(form).entries());
    for (const key of Object.keys(data)) {
        if (['client_id', 'car_id', 'work_id', 'part_id'].includes(key)) {
            data[key] = Number(data[key]);
        }
        if (['year', 'quantity', 'standard_hours', 'hourly_rate', 'price', 'quantity_in_stock'].includes(key)) {
            data[key] = Number(data[key]);
        }
        if (data[key] === '') {
            delete data[key];
        }
    }
    return data;
};

const statusClass = (status) => {
    if (['выполнен', 'закрыт'].includes(status)) return 'done';
    if (status === 'ожидание запчастей') return 'wait';
    if (status === 'отменен') return 'cancelled';
    return '';
};

const fillSelect = (selector, items, labelFn) => {
    const select = document.querySelector(selector);
    select.innerHTML = items.map((item) => `<option value="${item.id}">${labelFn(item)}</option>`).join('');
};

const carsForClient = (clientId) => state.cars.filter((car) => Number(car.client_id) === Number(clientId));

const priorityLabel = (value) => {
    if (value >= 75) return 'Высокий';
    if (value >= 50) return 'Средний';
    return 'Низкий';
};

const priorityClass = (value) => {
    if (value >= 75) return 'high';
    if (value >= 50) return 'medium';
    return 'low';
};

const opsActionButtons = (item, taskType) => `
    <div class="ops-actions">
        <button class="ghost small" data-ops-action="snoozed" data-task-key="${item.task_key}" data-task-type="${taskType}" type="button">Отложить</button>
        <button class="primary small" data-ops-action="done" data-task-key="${item.task_key}" data-task-type="${taskType}" type="button">Обработано</button>
    </div>
`;

const renderOpsCenter = () => {
    const descriptions = {
        radar: state.ops.radarDescription,
        priority: 'Очередь активных заказов по срочности и готовности.',
        stuck: 'Заказы, которые могут задержаться и требуют контроля.',
        maintenance: 'Клиенты, которым стоит предложить следующий визит или ТО.',
    };
    document.querySelector('#ops-description').textContent = descriptions[state.ops.activeTab] || '';
    document.querySelectorAll('[data-ops-tab]').forEach((button) => {
        button.classList.toggle('active', button.dataset.opsTab === state.ops.activeTab);
    });

    const content = document.querySelector('#ops-content');
    if (state.ops.activeTab === 'radar') {
        content.className = 'ops-content radar-list';
        content.innerHTML = state.ops.radar.map((item) => `
            <div class="radar-item">
            <div>
                <strong>${item.client}</strong>
                <span>${item.car} · ${item.phone}</span>
            </div>
            <div class="radar-score ${priorityClass(item.priority)}">${priorityLabel(item.priority)}</div>
            <p>${item.action}</p>
            <small>${item.reason}</small>
            ${opsActionButtons(item, 'radar')}
        </div>
        `).join('') || '<p class="hint">Нет срочных рекомендаций</p>';
        return;
    }

    content.className = 'ops-content compact-list columns';
    if (state.ops.activeTab === 'priority') {
        content.innerHTML = state.ops.priority.map((item) => `
            <div class="compact-item">
                <strong>#${item.order_id} · ${item.car}</strong>
                <span>${item.status} · ${item.mechanic} · ${priorityLabel(item.priority)} приоритет</span>
                <p>${item.next_action}</p>
                ${opsActionButtons(item, 'priority')}
            </div>
        `).join('') || '<p class="hint">Нет активных заказов</p>';
    } else if (state.ops.activeTab === 'stuck') {
        content.innerHTML = state.ops.stuck.map((item) => `
            <div class="compact-item">
                <strong>#${item.order_id} · ${item.client}</strong>
                <span>${item.status} · ${item.age_days} дн.</span>
                <p>${item.action}</p>
                ${opsActionButtons(item, 'stuck')}
            </div>
        `).join('') || '<p class="hint">Зависших заказов нет</p>';
    } else {
        content.innerHTML = state.ops.maintenance.map((item) => `
            <div class="compact-item">
                <strong>${item.client}</strong>
                <span>${item.car} · ${item.phone}</span>
                <p>${item.recommendation}</p>
                ${opsActionButtons(item, 'maintenance')}
            </div>
        `).join('') || '<p class="hint">Рекомендаций пока нет</p>';
    }
};

const renderDashboard = async () => {
    const [dashboard, radar, priority, stuck, maintenance] = await Promise.all([
        api('/api/dashboard'),
        api('/api/service-radar'),
        api('/api/orders/priority'),
        api('/api/orders/stuck'),
        api('/api/maintenance/recommendations'),
    ]);
    document.querySelector('#kpi-grid').innerHTML = [
        ['Клиентов', dashboard.clients],
        ['Автомобилей', dashboard.cars],
        ['Активных заказов', dashboard.active_orders],
        ['Выручка выполненных', money(dashboard.revenue)],
        ['Стоимость склада', money(dashboard.stock_value)],
        ['Позиции с низким остатком', dashboard.low_stock_parts],
        ['Всего заказов', dashboard.orders],
        ['Снижение складских ошибок', `${dashboard.kpi.stock_errors_reduction_percent}%`],
    ].map(([label, value]) => `<div class="kpi"><strong>${value}</strong><span>${label}</span></div>`).join('');

    state.ops.radar = radar.items;
    state.ops.radarDescription = radar.description;
    state.ops.priority = priority.items;
    state.ops.stuck = stuck.items;
    state.ops.maintenance = maintenance.items;
    renderOpsCenter();
};

const renderClients = () => {
    document.querySelector('#clients-cars-table').innerHTML = state.clients.map((client) => {
        const clientCars = carsForClient(client.id);
        const carsHtml = clientCars.length
            ? clientCars.map((car, index) => `
                <div class="car-chip">
                    <span>
                        <strong>${car.license_plate}</strong> ${car.model}${car.year ? `, ${car.year}` : ''}
                        ${index === 0 && clientCars.length > 1 ? `<em>+${clientCars.length - 1} ещё</em>` : ''}
                    </span>
                    <div class="car-actions">
                        <button class="ghost small" data-car-health="${car.id}" type="button">Медкарта</button>
                        <button class="danger small" data-delete-url="/api/cars/${car.id}" data-delete-name="автомобиль ${car.license_plate}" type="button">Удалить авто</button>
                    </div>
                </div>
            `).join('')
            : '<span class="muted">Автомобили не добавлены</span>';
        return `
            <tr>
                <td><strong>${client.name}</strong></td>
                <td>${client.phone}<br><span class="muted">${client.email || ''}</span></td>
                <td>
                    <div class="car-list collapsed ${clientCars.length > 1 ? 'expandable' : ''}" data-client-cars="${client.id}" id="client-cars-${client.id}">
                        ${carsHtml}
                    </div>
                </td>
                <td class="action-cell"><button class="danger small" data-delete-url="/api/clients/${client.id}" data-delete-name="клиента ${client.name}" type="button">Удалить клиента</button></td>
            </tr>
        `;
    }).join('');
    fillSelect('#car-client', state.clients, (client) => `${client.name} (${client.phone})`);
    fillSelect('#order-client', state.clients, (client) => client.name);
};

const renderCars = () => {
    const selectedClientId = document.querySelector('#order-client').value || state.clients[0]?.id;
    const cars = selectedClientId ? carsForClient(selectedClientId) : state.cars;
    fillSelect('#order-car', cars, (car) => `${car.license_plate} ${car.model}`);
};

const renderWorks = () => {
    document.querySelector('#works-table').innerHTML = state.works.map((work) => `
        <tr>
            <td>${work.name}</td>
            <td>${work.hours}</td>
            <td>${money(work.rate)}</td>
            <td><button class="danger small" data-delete-url="/api/works/${work.id}" data-delete-name="работу ${work.name}">Удалить</button></td>
        </tr>
    `).join('');
};

const renderMechanics = () => {
    fillSelect('#order-mechanic', [{ id: '', name: 'Не назначен', specialization: '' }, ...state.mechanics], (item) => (
        item.id ? `${item.name} · ${item.specialization}` : item.name
    ));
    document.querySelector('#mechanics-table').innerHTML = state.mechanics.map((item) => `
        <tr>
            <td>${item.name}</td>
            <td>${item.specialization}</td>
            <td>${item.phone || ''}</td>
            <td><button class="danger small" data-delete-url="/api/mechanics/${item.id}" data-delete-name="мастера ${item.name}" type="button">Удалить</button></td>
        </tr>
    `).join('');
};

const renderParts = () => {
    document.querySelector('#parts-table').innerHTML = state.parts.map((part) => `
        <tr>
            <td>${part.name}</td>
            <td>${part.sku || ''}</td>
            <td>${money(part.price)}</td>
            <td>${part.stock}</td>
            <td><button class="danger small" data-delete-url="/api/parts/${part.id}" data-delete-name="запчасть ${part.name}">Удалить</button></td>
        </tr>
    `).join('');
};

const renderPartsForecast = async () => {
    const forecast = await api('/api/parts/forecast');
    document.querySelector('#parts-forecast').innerHTML = forecast.items.map((item) => `
        <div class="compact-item risk-${item.risk}">
            <strong>${item.name}</strong>
            <span>${item.sku || ''} · остаток ${item.stock} · хватит на ${item.orders_left} заказ(а)</span>
            <p>${item.action}</p>
        </div>
    `).join('') || '<p class="hint">Нет данных для прогноза</p>';
};

const renderOrders = () => {
    const filter = document.querySelector('#status-filter').value;
    const rows = state.orders
        .filter((order) => !filter || order.status === filter)
        .map((order) => `
            <tr data-order-id="${order.id}">
                <td>#${order.id}</td>
                <td>${order.client}</td>
                <td>${order.car}</td>
                <td>${order.mechanic}</td>
                <td><span class="status ${statusClass(order.status)}">${order.status}</span></td>
                <td>${money(order.total)}</td>
                <td><button class="danger small" data-delete-url="/api/orders/${order.id}" data-delete-name="заказ #${order.id}">Удалить</button></td>
            </tr>
        `).join('');
    document.querySelector('#orders-table').innerHTML = rows;
};

const renderStatusFilter = () => {
    const select = document.querySelector('#status-filter');
    select.innerHTML = '<option value="">Все статусы</option>' + statuses
        .map((status) => `<option value="${status}">${status}</option>`)
        .join('');
};

const renderOrderDetail = async (orderId) => {
    state.selectedOrderId = orderId;
    const [order, insight] = await Promise.all([
        api(`/api/orders/${orderId}`),
        api(`/api/orders/${orderId}/insight`),
    ]);
    const workOptions = state.works.map((work) => `<option value="${work.id}">${work.name}</option>`).join('');
    const partOptions = state.parts.map((part) => `<option value="${part.id}">${part.name} (${part.stock} шт.)</option>`).join('');
    const statusOptions = statuses
        .map((status) => `<option value="${status}" ${status === order.status ? 'selected' : ''}>${status}</option>`)
        .join('');
    const mechanicOptions = [
        '<option value="">Не назначен</option>',
        ...state.mechanics.map((item) => `<option value="${item.id}" ${order.mechanic?.id === item.id ? 'selected' : ''}>${item.name} · ${item.specialization}</option>`)
    ].join('');

    document.querySelector('#order-detail').classList.remove('empty');
    document.querySelector('#order-detail').innerHTML = `
        <div class="panel-head">
            <div>
                <p class="eyebrow">Заказ #${order.id}</p>
                <h3>${order.client.name} · ${order.car.license_plate} ${order.car.model}</h3>
                <p class="hint">Мастер: ${order.mechanic ? `${order.mechanic.name} · ${order.mechanic.specialization}` : 'не назначен'}</p>
            </div>
            <span class="status ${statusClass(order.status)}">${order.status}</span>
        </div>
        <section class="insight-card">
            <div>
                <p class="eyebrow">Киллер-фича</p>
                <h3>${insight.killer_feature}</h3>
                <p>${insight.business_effect}</p>
            </div>
            <div class="readiness">
                <strong>${insight.readiness_score}%</strong>
                <span>готовность</span>
            </div>
            <div class="next-action">
                <span>Риск: ${insight.risk_level}</span>
                <strong>${insight.next_action}</strong>
                <small>${insight.score_explanation}</small>
            </div>
        </section>
        <div class="checklist">
            ${insight.checklist.map((item) => `
                <span class="${item.ok ? 'ok' : 'warn'}">${item.ok ? '✓' : '!'} ${item.label}</span>
            `).join('')}
        </div>
        <div class="detail-grid">
            <div>
                <h3>Работы</h3>
                <table>
                    <tbody>
                        ${order.works.map((item) => `
                            <tr>
                                <td>${item.name}</td>
                                <td>${item.quantity}</td>
                                <td>${money(item.standard_hours * item.hourly_rate * item.quantity)}</td>
                                <td><button class="danger small" data-order-item-delete="/api/orders/${order.id}/works/${item.id}" data-delete-name="работу ${item.name}" type="button">Удалить</button></td>
                            </tr>
                        `).join('') || '<tr><td>Работы не добавлены</td></tr>'}
                    </tbody>
                </table>
                <form class="mini-form" id="add-work-form">
                    <label>Работа<select name="work_id">${workOptions}</select></label>
                    <label>Кол-во<input name="quantity" type="number" min="1" value="1"></label>
                    <button class="primary" type="submit">Добавить</button>
                </form>
            </div>
            <div>
                <h3>Запчасти</h3>
                <table>
                    <tbody>
                        ${order.parts.map((item) => `
                            <tr>
                                <td>${item.name}</td>
                                <td>резерв ${item.quantity_reserved}</td>
                                <td>исп. ${item.quantity_used}</td>
                                <td><button class="danger small" data-order-item-delete="/api/orders/${order.id}/parts/${item.id}" data-delete-name="запчасть ${item.name}" type="button">Удалить</button></td>
                            </tr>
                        `).join('') || '<tr><td>Запчасти не добавлены</td></tr>'}
                    </tbody>
                </table>
                <form class="mini-form" id="add-part-form">
                    <label>Запчасть<select name="part_id">${partOptions}</select></label>
                    <label>Кол-во<input name="quantity" type="number" min="0.1" step="0.1" value="1"></label>
                    <button class="primary" type="submit">В резерв</button>
                </form>
            </div>
        </div>
        <div class="actions">
            <select id="order-mechanic-edit">${mechanicOptions}</select>
            <button class="primary" id="save-mechanic" type="button">Назначить мастера</button>
            <select id="order-status">${statusOptions}</select>
            <button class="primary" id="save-status" type="button">Сменить статус</button>
            <a class="ghost" href="/api/orders/${order.id}/document?format=html" target="_blank">HTML</a>
            <a class="ghost" href="/api/orders/${order.id}/document?format=pdf" target="_blank">PDF</a>
            <button class="danger" data-delete-url="/api/orders/${order.id}" data-delete-name="заказ #${order.id}" type="button">Удалить заказ</button>
            <strong>Итого: ${money(order.total)}</strong>
        </div>
    `;
};

const loadAll = async () => {
    const [clients, cars, works, parts, mechanics, orders] = await Promise.all([
        api('/api/clients'),
        api('/api/cars'),
        api('/api/works'),
        api('/api/parts'),
        api('/api/mechanics'),
        api('/api/orders'),
    ]);
    Object.assign(state, { clients, cars, works, parts, mechanics, orders });
    await renderDashboard();
    renderClients();
    renderCars();
    renderWorks();
    renderMechanics();
    renderParts();
    await renderPartsForecast();
    renderOrders();
};

const postForm = (selector, url, message) => {
    document.querySelector(selector).addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
            await api(url, { method: 'POST', body: JSON.stringify(asJson(event.target)) });
            event.target.reset();
            await loadAll();
            toast(message);
        } catch (error) {
            toast(error.message);
        }
    });
};

document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
        document.querySelectorAll('.section').forEach((section) => section.classList.remove('active'));
        tab.classList.add('active');
        document.querySelector(`#${tab.dataset.section}`).classList.add('active');
    });
});

document.querySelector('#orders-table').addEventListener('click', async (event) => {
    if (event.target.closest('[data-delete-url]')) return;
    const row = event.target.closest('tr[data-order-id]');
    if (row) {
        await renderOrderDetail(row.dataset.orderId);
    }
});

document.querySelector('#order-detail').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
        const endpoint = form.id === 'add-work-form' ? 'add_work' : 'add_part';
        await api(`/api/orders/${state.selectedOrderId}/${endpoint}`, {
            method: 'POST',
            body: JSON.stringify(asJson(form)),
        });
        await loadAll();
        await renderOrderDetail(state.selectedOrderId);
        toast('Заказ обновлен');
    } catch (error) {
        toast(error.message);
    }
});

document.querySelector('#order-detail').addEventListener('click', async (event) => {
    const deleteButton = event.target.closest('[data-order-item-delete]');
    if (deleteButton) {
        const name = deleteButton.dataset.deleteName || 'позицию заказа';
        if (!confirm(`Удалить ${name} из заказа?`)) return;
        try {
            await api(deleteButton.dataset.orderItemDelete, { method: 'DELETE' });
            await loadAll();
            await renderOrderDetail(state.selectedOrderId);
            toast('Позиция удалена из заказа');
        } catch (error) {
            toast(error.message);
        }
        return;
    }

    if (event.target.id === 'save-mechanic') {
        try {
            await api(`/api/orders/${state.selectedOrderId}/mechanic`, {
                method: 'PUT',
                body: JSON.stringify({ mechanic_id: document.querySelector('#order-mechanic-edit').value || null }),
            });
            await loadAll();
            await renderOrderDetail(state.selectedOrderId);
            toast('Мастер назначен');
        } catch (error) {
            toast(error.message);
        }
        return;
    }

    if (event.target.id !== 'save-status') return;
    try {
        await api(`/api/orders/${state.selectedOrderId}/status`, {
            method: 'PUT',
            body: JSON.stringify({ status: document.querySelector('#order-status').value }),
        });
        await loadAll();
        await renderOrderDetail(state.selectedOrderId);
        toast('Статус изменен');
    } catch (error) {
        toast(error.message);
    }
});

document.querySelector('#status-filter').addEventListener('change', renderOrders);
document.querySelector('#refresh-btn').addEventListener('click', loadAll);
document.querySelector('#order-client').addEventListener('change', renderCars);
document.querySelectorAll('[data-ops-tab]').forEach((button) => {
    button.addEventListener('click', () => {
        state.ops.activeTab = button.dataset.opsTab;
        renderOpsCenter();
    });
});
document.querySelector('#logout-btn').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => null);
    showLogin();
    toast('Вы вышли из системы');
});

document.querySelector('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        await api('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify(asJson(event.target)),
        });
        event.target.reset();
        showApp();
        await loadAll();
        toast('Вход выполнен');
    } catch (error) {
        toast(error.message);
    }
});

document.addEventListener('click', async (event) => {
    const opsButton = event.target.closest('[data-ops-action]');
    if (opsButton) {
        try {
            await api('/api/ops/tasks', {
                method: 'POST',
                body: JSON.stringify({
                    task_key: opsButton.dataset.taskKey,
                    task_type: opsButton.dataset.taskType,
                    status: opsButton.dataset.opsAction,
                }),
            });
            await renderDashboard();
            toast(opsButton.dataset.opsAction === 'done' ? 'Карточка обработана' : 'Карточка отложена на 7 дней');
        } catch (error) {
            toast(error.message);
        }
        return;
    }

    const healthButton = event.target.closest('[data-car-health]');
    if (healthButton) {
        try {
            const health = await api(`/api/cars/${healthButton.dataset.carHealth}/health`);
            document.querySelector('#car-health-panel').classList.remove('hidden');
            document.querySelector('#car-health-content').innerHTML = `
                <div class="health-head">
                    <div>
                        <strong>${health.car}</strong>
                        <span>${health.client} · ${health.phone}</span>
                    </div>
                    <span class="status">${health.age ? `${health.age} лет` : 'год не указан'}</span>
                </div>
                <p>${health.recommendation}</p>
                <div class="compact-list">
                    ${health.timeline.map((item) => `
                        <div class="compact-item">
                            <strong>Заказ #${item.order_id} · ${item.status}</strong>
                            <span>${new Date(item.date).toLocaleDateString('ru-RU')} · ${money(item.total)}</span>
                            <p>${[...item.works, ...item.parts].join(', ') || 'Позиции не добавлены'}</p>
                        </div>
                    `).join('') || '<p class="hint">Истории заказов пока нет</p>'}
                </div>
            `;
        } catch (error) {
            toast(error.message);
        }
        return;
    }

    const carList = event.target.closest('.car-list[data-client-cars]');
    if (carList && !event.target.closest('[data-delete-url]') && !event.target.closest('[data-car-health]')) {
        carList.classList.toggle('collapsed');
        carList.classList.toggle('open');
        return;
    }

    const button = event.target.closest('[data-delete-url]');
    if (!button) return;
    const name = button.dataset.deleteName || 'запись';
    if (!confirm(`Удалить ${name}?`)) return;
    try {
        await api(button.dataset.deleteUrl, { method: 'DELETE' });
        if (button.dataset.deleteUrl.includes('/api/orders/') && Number(button.dataset.deleteUrl.split('/').pop()) === Number(state.selectedOrderId)) {
            state.selectedOrderId = null;
            document.querySelector('#order-detail').classList.add('empty');
            document.querySelector('#order-detail').textContent = 'Выберите заказ из списка';
        }
        await loadAll();
        toast('Данные удалены');
    } catch (error) {
        toast(error.message);
    }
});

postForm('#client-form', '/api/clients', 'Клиент добавлен');
postForm('#car-form', '/api/cars', 'Автомобиль добавлен');
postForm('#part-form', '/api/parts', 'Запчасть добавлена');
postForm('#work-form', '/api/works', 'Работа добавлена');
postForm('#order-form', '/api/orders', 'Заказ создан');
postForm('#mechanic-form', '/api/mechanics', 'Мастер добавлен');

document.querySelector('#complaint-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const result = await api('/api/complaints/suggest', {
            method: 'POST',
            body: JSON.stringify(asJson(event.target)),
        });
        document.querySelector('#complaint-suggestions').innerHTML = `
            <p class="hint">${result.reason}</p>
            ${result.suggestions.map((item) => `
                <div class="suggestion">
                    <strong>${item.name}</strong>
                    <span>${item.hours ? `${item.hours} н/ч · ${money(item.rate)}` : 'добавьте работу в справочник'}</span>
                </div>
            `).join('')}
        `;
    } catch (error) {
        toast(error.message);
    }
});

const init = async () => {
    renderStatusFilter();
    const auth = await api('/api/auth/me');
    if (!auth.authenticated) {
        showLogin();
        return;
    }
    showApp();
    await loadAll();
};

init().catch((error) => {
    showLogin();
    toast(error.message);
});
