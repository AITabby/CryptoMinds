// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CryptoMinds 多签仲裁合约
 *
 * 2-of-3 多签仲裁，替代 ServiceEscrow / ServiceEscrowV2 的 onlyOwner 单管理员模式。
 *
 * 流程：
 * 1. 仲裁员 proposeArbitration → 创建仲裁请求
 * 2. 另一个仲裁员 confirmArbitration → 达到阈值后自动执行
 * 3. 执行结果调用 escrow 合约的 arbitrateRelease 或 arbitrateRefund
 *
 * 紧急覆盖：admin 可直接执行（跳过多签），用于极端情况。
 */

interface IServiceEscrow {
    function arbitrateRelease(bytes32 orderId) external;
    function arbitrateRefund(bytes32 orderId, string calldata reason) external;
    function owner() external view returns (address);
}

contract MultiSigEscrowArbiter {

    address public admin;           // 紧急管理员（可跳过多签直接执行）
    address[3] public arbiters;     // 3 个仲裁员
    uint8 public required;          // 需要的确认数 (2)

    address public escrowContract;  // ServiceEscrow / V2 合约地址

    struct ArbitrationRequest {
        bytes32 orderId;
        bool isRefund;              // true = refund buyer, false = release to seller
        string reason;
        uint8 confirmationCount;
        bool executed;
        uint256 createdAt;
    }

    mapping(bytes32 => ArbitrationRequest) public requests;
    mapping(bytes32 => mapping(address => bool)) public confirmations;
    bytes32[] public requestIds;

    event ArbitrationProposed(bytes32 indexed requestId, bytes32 indexed orderId, bool isRefund, string reason, address indexed proposer);
    event ArbitrationConfirmed(bytes32 indexed requestId, address indexed confirmer, uint8 confirmationCount);
    event ArbitrationExecuted(bytes32 indexed requestId, bytes32 indexed orderId, bool isRefund);
    event EmergencyExecuted(bytes32 indexed orderId, bool isRefund, address indexed admin);
    event ArbiterUpdated(uint8 index, address oldArbiter, address newArbiter);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    modifier onlyArbiter() {
        require(_isArbiter(msg.sender), "Not arbiter");
        _;
    }

    constructor(address[3] memory _arbiters, address _escrowContract, address _admin) {
        require(_escrowContract != address(0), "Invalid escrow contract");
        for (uint8 i = 0; i < 3; i++) {
            require(_arbiters[i] != address(0), "Invalid arbiter");
            arbiters[i] = _arbiters[i];
        }
        escrowContract = _escrowContract;
        admin = _admin;
        required = 2;
    }

    function proposeArbitration(
        bytes32 orderId,
        bool isRefund,
        string calldata reason
    ) external onlyArbiter returns (bytes32 requestId) {
        requestId = keccak256(abi.encodePacked(orderId, isRefund, block.timestamp, requestIds.length));

        require(requests[requestId].createdAt == 0, "Request already exists");

        requests[requestId] = ArbitrationRequest({
            orderId: orderId,
            isRefund: isRefund,
            reason: reason,
            confirmationCount: 0,
            executed: false,
            createdAt: block.timestamp
        });
        requestIds.push(requestId);

        // Proposer auto-confirms
        _confirm(requestId);

        emit ArbitrationProposed(requestId, orderId, isRefund, reason, msg.sender);
    }

    function confirmArbitration(bytes32 requestId) external onlyArbiter {
        ArbitrationRequest storage req = requests[requestId];
        require(req.createdAt > 0, "Request not found");
        require(!req.executed, "Already executed");
        require(!confirmations[requestId][msg.sender], "Already confirmed");

        _confirm(requestId);

        emit ArbitrationConfirmed(requestId, msg.sender, req.confirmationCount);

        if (req.confirmationCount >= required) {
            _execute(requestId);
        }
    }

    function _confirm(bytes32 requestId) internal {
        confirmations[requestId][msg.sender] = true;
        requests[requestId].confirmationCount++;
    }

    function _execute(bytes32 requestId) internal {
        ArbitrationRequest storage req = requests[requestId];
        require(!req.executed, "Already executed");

        req.executed = true;

        IServiceEscrow escrow = IServiceEscrow(escrowContract);
        if (req.isRefund) {
            escrow.arbitrateRefund(req.orderId, req.reason);
        } else {
            escrow.arbitrateRelease(req.orderId);
        }

        emit ArbitrationExecuted(requestId, req.orderId, req.isRefund);
    }

    /**
     * 紧急执行 — 管理员可跳过多签直接仲裁
     * 仅用于极端情况（如仲裁员密钥丢失）
     */
    function emergencyExecute(bytes32 orderId, bool isRefund, string calldata reason) external onlyAdmin {
        IServiceEscrow escrow = IServiceEscrow(escrowContract);
        if (isRefund) {
            escrow.arbitrateRefund(orderId, reason);
        } else {
            escrow.arbitrateRelease(orderId);
        }

        emit EmergencyExecuted(orderId, isRefund, msg.sender);
    }

    function updateArbiter(uint8 index, address newArbiter) external onlyAdmin {
        require(index < 3, "Invalid index");
        require(newArbiter != address(0), "Zero address");
        address old = arbiters[index];
        arbiters[index] = newArbiter;
        emit ArbiterUpdated(index, old, newArbiter);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "Zero address");
        admin = newAdmin;
    }

    function getRequestCount() external view returns (uint256) {
        return requestIds.length;
    }

    function _isArbiter(address addr) internal view returns (bool) {
        return arbiters[0] == addr || arbiters[1] == addr || arbiters[2] == addr;
    }
}