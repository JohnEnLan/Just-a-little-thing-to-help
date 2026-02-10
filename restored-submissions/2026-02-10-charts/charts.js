/**
 * Green Campus - Person C: ECharts 可视化逻辑
 * 负责：获取数据、渲染图表、按钮交互及响应式调整。
 */

document.addEventListener('DOMContentLoaded', async () => {
    // --- 第一步：初始化与获取 DOM 元素 ---
    // 必须从 Person B 定义的 div 中读取 buildingId 
    const chartDiv = document.getElementById('chart-energy');
    if (!chartDiv) return;

    const buildingId = chartDiv.dataset.buildingId; // 读取 {{ building.id }} [cite: 269]
    const chart = echarts.init(chartDiv); // 初始化 ECharts 实例 [cite: 271]
    const btnDetect = document.getElementById('btn-detect'); // 异常检测按钮 [cite: 340]
    const tbody = document.getElementById('anomaly-table-body'); // 异常数据表格主体 [cite: 349]

    // --- 第二步：主加载函数 ---
    async function loadData() {
        try {
            // 并行调用两个 API 以提高效率 
            const [readingsRes, anomaliesRes] = await Promise.all([
                fetch(`/api/buildings/${buildingId}/readings`),
                fetch(`/api/buildings/${buildingId}/anomalies`)
            ]);

            const readingsData = await readingsRes.json();
            const anomaliesData = await anomaliesRes.json();

            // 执行渲染逻辑 [cite: 315]
            renderChart(readingsData.building_name, readingsData.readings, anomaliesData.anomalies);
            renderTable(anomaliesData.anomalies);
        } catch (error) {
            console.error("加载失败:", error);
            chartDiv.innerHTML = '<p style="color:red">数据加载失败，请检查后端服务器。</p>'; [cite: 370]
        }
    }

    // --- 第三步：ECharts 渲染逻辑 ---
    function renderChart(buildingName, readings, anomalies) {
        const option = {
            title: { text: '能耗趋势 - ' + buildingName }, [cite: 317]
            tooltip: { trigger: 'axis' }, [cite: 318]
            legend: { data: ['电耗 (kWh)', '检测到的异常'] }, [cite: 319]
            xAxis: { type: 'time' }, // 时间轴自动处理 ISO 8601 字符串 [cite: 320, 366]
            yAxis: { type: 'value', name: 'kWh' }, [cite: 321]
            series: [
                {
                    name: '电耗 (kWh)',
                    type: 'line',
                    smooth: true,
                    // 将原始数据映射为 [时间, 数值] 数组 [cite: 327]
                    data: readings.map(r => [r.timestamp, r.electricity_kwh])
                },
                {
                    name: '检测到的异常',
                    type: 'scatter',
                    symbolSize: 12,
                    itemStyle: { color: '#E53935' }, // 红色散点标识异常 [cite: 333]
                    // 同样映射异常数据 [cite: 334]
                    data: anomalies.map(a => [a.timestamp, a.electricity_kwh])
                }
            ]
        };
        chart.setOption(option); [cite: 338]
    }

    // --- 第四步：更新异常详情表格 ---
    function renderTable(anomalies) {
        tbody.innerHTML = ''; // 清空原有内容 [cite: 351]
        anomalies.forEach(a => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${a.timestamp}</td>
                <td>${a.electricity_kwh.toFixed(2)}</td>
                <td>${a.anomaly_score.toFixed(3)}</td>
            `; [cite: 354, 357]
            tbody.appendChild(row); [cite: 359]
        });
    }

    // --- 第五步：处理检测按钮交互 ---
    btnDetect.addEventListener('click', async () => {
        // 禁用按钮并显示加载状态 [cite: 342]
        btnDetect.disabled = true;
        btnDetect.innerText = "正在分析数据...";

        try {
            // 发送 POST 请求触发后端 scikit-learn 检测 [cite: 343]
            const response = await fetch(`/api/buildings/${buildingId}/detect`, { method: 'POST' });
            const result = await response.json();

            if (result.status === 'ok') {
                // 检测成功后，重新获取最新的异常数据并更新页面 [cite: 344]
                const freshRes = await fetch(`/api/buildings/${buildingId}/anomalies`);
                const freshData = await freshRes.json();
                
                // 更新图表（不合并，完全刷新异常点）和表格 [cite: 345, 346]
                renderChart(null, [], freshData.anomalies); 
                renderTable(freshData.anomalies);
                
                btnDetect.innerText = `检测完成：发现 ${result.anomalies_found} 处异常`; [cite: 347]
            }
        } catch (error) {
            alert("检测过程中发生错误，请查看控制台日志。"); [cite: 371]
        } finally {
            // 3秒后恢复按钮状态
            setTimeout(() => {
                btnDetect.disabled = false;
                btnDetect.innerText = "重新运行异常检测";
            }, 3000);
        }
    });

    // --- 第六步：响应式处理 ---
    // 监听窗口缩放，确保图表不会变形 [cite: 362]
    window.addEventListener('resize', () => chart.resize());

    // 页面加载时执行初始化
    loadData();
});