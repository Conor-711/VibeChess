// 多人游戏功能
(function() {
    // 全局变量
    let socket = null;
    let roomId = null;
    let playerColor = null;
    let isMultiplayerGame = false;
    let multiplayerGameStarted = false;
    let opponentName = '';
    let playerName = '';
    
    // 当页面加载完成后初始化多人游戏
    $(document).ready(function() {
        // 将多人游戏变量暴露给全局范围
        window.multiplayerGame = {
            isMultiplayerGame: function() { return isMultiplayerGame; },
            isGameStarted: function() { return multiplayerGameStarted; },
            getPlayerColor: function() { return playerColor; },
            getRoomId: function() { return roomId; },
            getSocket: function() { return socket; },
            handleMove: handleMove
        };
        
        // 添加多人游戏按钮
        const multiplayerBtn = $('<button id="multiplayerBtn" class="secondary"><i class="fas fa-users"></i> 多人游戏</button>');
        $('.controls').append(multiplayerBtn);
        
        // 显示多人游戏模态框
        $('#multiplayerBtn').click(function() {
            $('#multiplayerModal').css('display', 'flex');
            
            // 设置默认玩家昵称
            if (!$('#playerName').val()) {
                $('#playerName').val('玩家_' + Math.floor(Math.random() * 10000));
            }
        });
        
        // 关闭模态框
        $('.close-modal').click(function() {
            $('#multiplayerModal').hide();
        });
        
        // 显示加入房间表单
        $('#joinRoomBtn').click(function() {
            $('#createJoinOptions').hide();
            $('#joinRoomForm').show();
        });
        
        // 创建房间
        $('#createRoomBtn').click(function() {
            const variantState = $('#roomVariantState').val();
            playerName = $('#playerName').val() || '玩家_' + Math.floor(Math.random() * 10000);
            
            $.ajax({
                url: '/create_room',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ 
                    variant_state: variantState
                }),
                dataType: 'json'
            }).done(data => {
                roomId = data.room_id;
                $('#roomUrl').val(window.location.origin + data.join_url);
                $('#createJoinOptions').hide();
                $('#roomCreated').show();
                window.currentVariantState = variantState;
                
                // 更新浏览器URL
                window.history.pushState({}, '', data.join_url);
                
                // 初始化socket连接并加入房间
                initSocketIO();
                socket.emit('join', { 
                    room_id: roomId,
                    name: playerName
                });
                
                isMultiplayerGame = true;
                playerColor = 'white'; // 创建者默认为白方
                
                // 更新房间信息显示
                updateRoomInfoDisplay();
            });
        });
        
        // 复制房间链接
        $('#copyLinkBtn').click(function() {
            const roomUrl = $('#roomUrl');
            roomUrl.select();
            document.execCommand('copy');
            $(this).text('已复制!');
            setTimeout(() => $(this).text('复制链接'), 2000);
        });
        
        // 确认加入房间
        $('#confirmJoinBtn').click(function() {
            const inputRoomId = $('#roomIdInput').val().trim();
            if (!inputRoomId) return;
            
            window.location.href = `/room/${inputRoomId}`;
        });
        
        // 分享房间
        $('#shareRoomBtn').click(function() {
            const shareUrl = window.location.href;
            
            if (navigator.share) {
                navigator.share({
                    title: '在线象棋对战',
                    text: '加入我的象棋对战房间!',
                    url: shareUrl,
                });
            } else {
                // 回退到复制链接
                const tempInput = document.createElement('input');
                document.body.appendChild(tempInput);
                tempInput.value = shareUrl;
                tempInput.select();
                document.execCommand('copy');
                document.body.removeChild(tempInput);
                
                alert('链接已复制到剪贴板');
            }
        });
        
        // 离开房间
        $('#leaveRoomBtn').click(function() {
            if (confirm('确定要离开当前游戏房间吗?')) {
                window.location.href = '/';
            }
        });
        
        // 发送聊天消息
        $('#sendChatBtn').click(sendChatMessage);
        
        // 按Enter键发送消息
        $('#chatMessageInput').keypress(function(e) {
            if (e.which === 13) {
                sendChatMessage();
            }
        });
        
        // 切换聊天面板显示
        $('.toggle-chat').click(function() {
            $('.chat-body').toggleClass('collapsed');
            const icon = $(this).find('i');
            if (icon.hasClass('fa-chevron-down')) {
                icon.removeClass('fa-chevron-down').addClass('fa-chevron-up');
            } else {
                icon.removeClass('fa-chevron-up').addClass('fa-chevron-down');
            }
        });
        
        // 检查URL，如果是房间链接则初始化Socket
        const urlRoomId = getRoomIdFromUrl();
        if (urlRoomId) {
            initSocketIO();
        }
    });
    
    // 从URL中提取房间ID
    function getRoomIdFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/\/room\/([a-zA-Z0-9]+)/);
        return match ? match[1] : null;
    }
    
    // 处理多人游戏中的走棋
    function handleMove(source, target, piece, game) {
        if (!isMultiplayerGame || !multiplayerGameStarted) return false;
        
        // 检查是否轮到玩家
        const turn = game.turn() === 'w' ? 'white' : 'black';
        if (turn !== playerColor) {
            $('.message').text('现在不是您的回合').css('color', '#dc3545');
            return false;
        }
        
        // 尝试移动
        const move = game.move({
            from: source,
            to: target,
            promotion: 'q' // 默认升变为皇后
        });
        
        // 如果移动不合法
        if (!move) {
            return false;
        }
        
        // 发送移动到服务器
        socket.emit('move', { 
            room_id: roomId, 
            move: source + target,
            color: playerColor
        });
        
        // 显示等待对手的消息
        $('.message').text(`已走棋 ${move.san}，等待对手...`).css('color', '#6c757d');
        
        return true;
    }
    
    // 初始化Socket.IO
    function initSocketIO() {
        if (socket) return; // 已经初始化过
        
        socket = io();
        
        socket.on('connect', () => {
            console.log('已连接到服务器');
            
            // 如果URL中包含房间ID，则加入房间
            const urlRoomId = getRoomIdFromUrl();
            if (urlRoomId && !roomId) {
                roomId = urlRoomId;
                playerName = $('#playerName').val() || '玩家_' + Math.floor(Math.random() * 10000);
                
                socket.emit('join', { 
                    room_id: roomId,
                    name: playerName
                });
                
                isMultiplayerGame = true;
                
                // 显示多人游戏状态面板
                updateRoomInfoDisplay();
            }
        });
        
        socket.on('player_joined', (data) => {
            console.log('玩家加入:', data);
            
            // 更新玩家列表
            if (data.players) {
                data.players.forEach(player => {
                    if (player.color === 'white') {
                        $('.player.white .player-name').text(`白方: ${player.name}`);
                        if (playerColor !== 'white') {
                            opponentName = player.name;
                            playerColor = 'black'; // 如果不是房主，就是黑方
                        }
                    } else {
                        $('.player.black .player-name').text(`黑方: ${player.name}`);
                        if (playerColor !== 'black') {
                            opponentName = player.name;
                        }
                    }
                });
            }
            
            // 房间创建者看到有人加入的提示
            if (playerColor === 'white' && data.color === 'black') {
                $('.player-slot.black .player-name').text(`黑方: ${data.name}`);
                $('.player-slot.black .status').text('已加入').removeClass('waiting').addClass('ready');
                $('.waiting-message').text('对手已加入，游戏即将开始!');
                opponentName = data.name;
            }
            
            $('.message').text(`玩家已加入(${data.players_count}/2)`).css('color', '#28a745');
        });
        
        socket.on('game_start', (data) => {
            console.log('游戏开始:', data);
            
            // 设置游戏状态
            multiplayerGameStarted = true;
            window.currentVariantState = data.variant_state;
            
            // 重置棋盘为初始状态
            window.board.position(data.fen);
            window.game.load(data.fen);
            
            // 初始化棋子
            window.initPieces();
            
            // 隐藏等待界面
            $('#multiplayerModal').hide();
            
            // 显示游戏状态和聊天
            $('.multiplayer-status').show();
            $('.multiplayer-chat').show();
            
            // 更新游戏信息显示
            window.updateVariantStateInfo();
            $('.game-status').text('游戏已开始');
            $('.message').text(`与 ${opponentName} 的对战已开始!`).css('color', '#28a745');
            
            // 添加聊天系统消息
            addSystemChatMessage('游戏开始!');
        });
        
        socket.on('move_made', (data) => {
            console.log('收到走棋:', data);
            
            if (!multiplayerGameStarted) return;
            
            // 获取当前走棋方
            const currentTurn = data.turn;  // 服务器返回的下一个回合
            
            // 如果是对手走的棋
            if ((playerColor === 'white' && currentTurn === 'white') ||
                (playerColor === 'black' && currentTurn === 'black')) {
                
                // 更新棋盘
                try {
                    window.game.move({
                        from: data.from,
                        to: data.to,
                        promotion: data.move.length > 4 ? data.move.substring(4, 5) : 'q'
                    });
                } catch (e) {
                    console.error('走棋错误:', e);
                    // 如果走法不合法，使用FEN同步
                    window.game.load(data.fen);
                }
                
                // 更新棋盘显示
                window.board.position(window.game.fen());
                
                // 高亮显示上一步
                window.highlightLast(data.from, data.to);
                
                // 更新棋子位置映射
                const moverId = window.pieceMap[data.from];
                if (moverId) {
                    delete window.pieceMap[data.from];
                    window.pieceMap[data.to] = moverId;
                    // 如果有吃子，更新分数
                    const lastMove = window.game.history({verbose: true}).pop();
                    if (lastMove && lastMove.captured) {
                        window.scoreMap[moverId] += window.values[lastMove.captured];
                    }
                    window.updateLeaderboard();
                }
                
                // 添加到历史记录
                const moveText = window.game.history().pop() || `${data.from}-${data.to}`;
                window.appendHistory(moveText);
                
                // 添加聊天系统消息
                addSystemChatMessage(`${opponentName} 移动了 ${moveText}`);
                
                // 检查游戏结束
                window.checkGameOver();
                
                // 提示当前轮到玩家走棋
                if (!window.gameOver) {
                    $('.message').text(`轮到您走棋`).css('color', '#007bff');
                }
            }
        });
        
        socket.on('game_over', (data) => {
            window.gameOver = true;
            
            let resultText = "";
            if (data.result === 'checkmate') {
                if (data.winner === playerColor) {
                    resultText = "您赢了!";
                } else {
                    resultText = "您输了!";
                }
            } else {
                resultText = "平局!";
            }
            
            $('.game-status').text(`游戏结束: ${resultText}`);
            $('.message').text(resultText).css('color', data.winner === playerColor ? '#28a745' : '#dc3545');
            
            // 添加聊天系统消息
            addSystemChatMessage(`游戏结束: ${resultText}`);
        });
        
        socket.on('player_left', (data) => {
            console.log('玩家离开:', data);
            
            // 显示对手离开的消息
            $('.message').text(`对手 ${data.name} 已离开游戏`).css('color', '#dc3545');
            
            // 添加聊天系统消息
            addSystemChatMessage(`${data.name} 离开了游戏`);
            
            // 如果游戏已经开始，则标记为结束
            if (multiplayerGameStarted) {
                window.gameOver = true;
                $('.game-status').text('对手已离开');
            }
            
            // 更新玩家信息显示
            if (data.color === 'white') {
                $('.player.white .player-name').text('白方: 已离开');
                $('.player.white .player-status').text('离线');
            } else {
                $('.player.black .player-name').text('黑方: 已离开');
                $('.player.black .player-status').text('离线');
            }
        });
        
        socket.on('chat_message', (data) => {
            console.log('收到聊天消息:', data);
            
            const isFromSelf = data.color === playerColor;
            const messageClass = isFromSelf ? 'self' : 'other';
            const messageHtml = `
                <div class="chat-message ${messageClass}">
                    <div class="message-info">${data.sender} (${data.color === 'white' ? '白方' : '黑方'})</div>
                    <div class="message-text">${escapeHtml(data.message)}</div>
                </div>
            `;
            
            $('#multiplayerChatMessages').append(messageHtml);
            scrollChatToBottom();
        });
        
        socket.on('error', (data) => {
            console.error('错误:', data);
            $('.message').text(data.message).css('color', '#dc3545');
        });
        
        socket.on('disconnect', () => {
            console.log('与服务器断开连接');
            $('.message').text('与服务器的连接已断开，请刷新页面').css('color', '#dc3545');
        });
    }
    
    // 添加系统消息到聊天区
    function addSystemChatMessage(message) {
        const messageHtml = `
            <div class="chat-message system">
                <div class="message-info">系统消息</div>
                <div class="message-text">${message}</div>
            </div>
        `;
        
        $('#multiplayerChatMessages').append(messageHtml);
        scrollChatToBottom();
    }
    
    // 滚动聊天到底部
    function scrollChatToBottom() {
        const chatMessages = document.getElementById('multiplayerChatMessages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
    
    // 转义HTML
    function escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
    
    // 更新房间信息显示
    function updateRoomInfoDisplay() {
        $('.multiplayer-status').show();
        $('#currentRoomId').text(roomId);
        
        // 设置玩家信息
        if (playerColor === 'white') {
            $('.player.white .player-name').text(`白方: ${playerName} (您)`);
            $('.player.black .player-name').text('黑方: 等待加入...');
        } else if (playerColor === 'black') {
            $('.player.white .player-name').text('白方: 等待中...');
            $('.player.black .player-name').text(`黑方: ${playerName} (您)`);
        }
    }
    
    // 发送聊天消息的函数
    function sendChatMessage() {
        const message = $('#chatMessageInput').val().trim();
        if (!message || !socket || !roomId) return;
        
        socket.emit('chat_message', {
            room_id: roomId,
            message: message
        });
        
        $('#chatMessageInput').val('');
    }
})(); 