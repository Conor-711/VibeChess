"""
Stockfish mock implementation for environments where Stockfish binary is not available.
This provides a simplified implementation that can be used as a fallback.
"""
import random
import chess

class StockfishMock:
    """Mock implementation of Stockfish for environments where the binary is not available."""
    
    def __init__(self, path=None, depth=10, parameters=None):
        self.board = chess.Board()
        self.skill_level = 5
        self.depth = depth
        self.parameters = parameters or {}
        print("Using StockfishMock as fallback (Stockfish binary not available)")
    
    def set_skill_level(self, skill_level):
        """Set the skill level of the engine."""
        self.skill_level = skill_level
        print(f"StockfishMock: Set skill level to {skill_level}")
    
    def set_fen_position(self, fen_position):
        """Set the board position in Forsyth-Edwards Notation (FEN)."""
        try:
            self.board = chess.Board(fen_position)
        except ValueError as e:
            print(f"StockfishMock: Invalid FEN position: {e}")
    
    def get_best_move(self):
        """Get the best move in the current position."""
        legal_moves = list(self.board.legal_moves)
        if not legal_moves:
            return None
        
        # Simple strategy: prefer captures and checks
        captures = [move for move in legal_moves if self.board.is_capture(move)]
        checks = [move for move in legal_moves if self.board.gives_check(move)]
        
        # Prioritize captures and checks based on skill level
        if captures and random.random() < 0.7 + (self.skill_level / 20):
            return captures[random.randint(0, len(captures) - 1)].uci()
        elif checks and random.random() < 0.6 + (self.skill_level / 20):
            return checks[random.randint(0, len(checks) - 1)].uci()
        else:
            return legal_moves[random.randint(0, len(legal_moves) - 1)].uci()
    
    def get_evaluation(self):
        """Get a simple evaluation of the current position."""
        # Count material difference as a simple evaluation
        pawns = len(self.board.pieces(chess.PAWN, chess.WHITE)) - len(self.board.pieces(chess.PAWN, chess.BLACK))
        knights = len(self.board.pieces(chess.KNIGHT, chess.WHITE)) - len(self.board.pieces(chess.KNIGHT, chess.BLACK))
        bishops = len(self.board.pieces(chess.BISHOP, chess.WHITE)) - len(self.board.pieces(chess.BISHOP, chess.BLACK))
        rooks = len(self.board.pieces(chess.ROOK, chess.WHITE)) - len(self.board.pieces(chess.ROOK, chess.BLACK))
        queens = len(self.board.pieces(chess.QUEEN, chess.WHITE)) - len(self.board.pieces(chess.QUEEN, chess.BLACK))
        
        # Simple material count (standard piece values)
        score = pawns + 3 * knights + 3 * bishops + 5 * rooks + 9 * queens
        
        # Add some randomness based on inverse of skill level
        randomness = (20 - self.skill_level) / 10
        score += random.uniform(-randomness, randomness)
        
        # Return in the format expected by the application
        if score > 0:
            return {"type": "cp", "value": int(score * 100)}
        else:
            return {"type": "cp", "value": int(score * 100)}
    
    def set_position(self, position):
        """Set the board position from a list of moves."""
        self.board = chess.Board()
        for move in position:
            try:
                self.board.push_san(move)
            except ValueError:
                try:
                    self.board.push_uci(move)
                except ValueError:
                    print(f"StockfishMock: Invalid move: {move}")
    
    def get_board_visual(self):
        """Get a string representation of the board."""
        return str(self.board)
    
    def set_depth(self, depth):
        """Set the depth of the engine."""
        self.depth = depth
    
    def get_parameters(self):
        """Get the parameters of the engine."""
        return self.parameters
    
    def set_parameter(self, name, value):
        """Set a parameter of the engine."""
        self.parameters[name] = value
    
    def get_stockfish_major_version(self):
        """Get the major version of Stockfish."""
        return 15  # Mock version
