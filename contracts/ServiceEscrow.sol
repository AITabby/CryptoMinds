// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CryptoMinds 服务担保合约 (ServiceEscrow)
 * 
 * 资金安全第一 —— 买卖双方都有保障。
 * 
 * 流程：
 * 1. 买家创建订单，BNB 锁入合约
 * 2. 卖家提交服务结果
 * 3. 买家确认收货 → BNB 释放给卖家
 * 4. 超时自动确认 → BNB 释放给卖家
 * 5. 买家争议 → 管理员仲裁（退款或放款）
 * 
 * 不需要发币，全程 BNB。
 */
contract ServiceEscrow {
    
    address public owner;           // 管理员（仲裁者）
    uint256 public defaultTimeout;  // 默认超时（秒）
    
    enum OrderStatus { 
        None,           // 不存在
        Pending,        // 等待卖家接单
        Delivering,     // 卖家已接单，执行中
        Delivered,      // 卖家已提交结果
        Confirmed,      // 买家确认收货，已放款
        Disputed,       // 买家争议，等仲裁
        Refunded,       // 仲裁退款给买家
        Expired         // 超时自动确认
    }
    
    struct Order {
        address buyer;          // 买家钱包
        address seller;         // 卖家钱包
        string serviceId;       // 服务 ID
        uint256 amount;         // 担保金额 (wei)
        uint256 createdAt;      // 创建时间
        uint256 deliveredAt;    // 卖家提交时间
        uint256 timeoutAt;      // 超时时间
        OrderStatus status;     // 当前状态
        string deliverResult;   // 卖家提交的结果（哈希或简述）
    }
    
    // orderId => Order
    mapping(bytes32 => Order) public orders;
    bytes32[] public allOrderIds;
    
    // 统计
    uint256 public totalEscrowed;      // 累计担保金额
    uint256 public totalReleased;      // 累计释放给卖家
    uint256 public totalRefunded;      // 累计退款给买家
    uint256 public totalDisputed;      // 累计争议数
    
    // 事件
    event OrderCreated(bytes32 indexed orderId, address indexed buyer, address indexed seller, string serviceId, uint256 amount);
    event OrderDelivered(bytes32 indexed orderId, string deliverResult);
    event OrderConfirmed(bytes32 indexed orderId, uint256 amount);
    event OrderDisputed(bytes32 indexed orderId, address indexed buyer);
    event OrderRefunded(bytes32 indexed orderId, uint256 amount, string reason);
    event OrderExpired(bytes32 indexed orderId, uint256 amount);
    event TimeoutUpdated(uint256 oldTimeout, uint256 newTimeout);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    modifier onlyBuyer(bytes32 orderId) {
        require(msg.sender == orders[orderId].buyer, "Not buyer");
        _;
    }
    
    modifier onlySeller(bytes32 orderId) {
        require(msg.sender == orders[orderId].seller, "Not seller");
        _;
    }
    
    constructor(uint256 _defaultTimeout) {
        owner = msg.sender;
        defaultTimeout = _defaultTimeout > 0 ? _defaultTimeout : 24 hours;
    }
    
    /**
     * 买家创建担保订单
     * @param seller 卖家钱包地址
     * @param serviceId 服务 ID
     * @param timeoutSeconds 超时时间（秒），0 使用默认值
     * @return orderId 订单 ID
     */
    function createOrder(
        address seller,
        string calldata serviceId,
        uint256 timeoutSeconds
    ) external payable returns (bytes32 orderId) {
        require(msg.value > 0, "Must deposit > 0");
        require(seller != address(0), "Invalid seller");
        require(seller != msg.sender, "Cannot buy from self");
        require(bytes(serviceId).length > 0, "Invalid serviceId");
        
        orderId = keccak256(abi.encodePacked(
            msg.sender,
            seller,
            serviceId,
            block.timestamp,
            allOrderIds.length
        ));
        
        uint256 timeout = timeoutSeconds > 0 ? timeoutSeconds : defaultTimeout;
        
        Order memory order = Order({
            buyer: msg.sender,
            seller: seller,
            serviceId: serviceId,
            amount: msg.value,
            createdAt: block.timestamp,
            deliveredAt: 0,
            timeoutAt: block.timestamp + timeout,
            status: OrderStatus.Pending,
            deliverResult: ""
        });
        
        orders[orderId] = order;
        allOrderIds.push(orderId);
        totalEscrowed += msg.value;
        
        emit OrderCreated(orderId, msg.sender, seller, serviceId, msg.value);
    }
    
    /**
     * 卖家提交服务结果
     * @param orderId 订单 ID
     * @param result 服务结果（哈希或简述）
     */
    function deliver(bytes32 orderId, string calldata result) external onlySeller(orderId) {
        Order storage order = orders[orderId];
        require(order.status == OrderStatus.Pending, "Order not pending");
        
        order.status = OrderStatus.Delivered;
        order.deliveredAt = block.timestamp;
        order.deliverResult = result;
        
        emit OrderDelivered(orderId, result);
    }
    
    /**
     * 买家确认收货 → BNB 释放给卖家
     * @param orderId 订单 ID
     */
    function confirm(bytes32 orderId) external onlyBuyer(orderId) {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Delivered,
            "Order not delivered"
        );
        
        order.status = OrderStatus.Confirmed;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;
        
        (bool ok, ) = payable(order.seller).call{value: amount}("");
        require(ok, "Transfer to seller failed");
        
        emit OrderConfirmed(orderId, amount);
    }
    
    /**
     * 买家发起争议
     * @param orderId 订单 ID
     */
    function dispute(bytes32 orderId) external onlyBuyer(orderId) {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Delivered,
            "Order not delivered"
        );
        
        order.status = OrderStatus.Disputed;
        totalDisputed += 1;
        
        emit OrderDisputed(orderId, msg.sender);
    }
    
    /**
     * 超时自动确认 → BNB 释放给卖家
     * 任何人都可以调用
     * @param orderId 订单 ID
     */
    function claimTimeout(bytes32 orderId) external {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Delivered,
            "Order not delivered"
        );
        require(block.timestamp >= order.timeoutAt, "Not timed out yet");
        
        order.status = OrderStatus.Expired;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;
        
        (bool ok, ) = payable(order.seller).call{value: amount}("");
        require(ok, "Transfer to seller failed");
        
        emit OrderExpired(orderId, amount);
    }
    
    /**
     * 管理员仲裁 —— 退款给买家
     * @param orderId 订单 ID
     * @param reason 仲裁原因
     */
    function arbitrateRefund(bytes32 orderId, string calldata reason) external onlyOwner {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Disputed,
            "Order not disputed"
        );
        
        order.status = OrderStatus.Refunded;
        uint256 amount = order.amount;
        order.amount = 0;
        totalRefunded += amount;
        
        (bool ok, ) = payable(order.buyer).call{value: amount}("");
        require(ok, "Transfer to buyer failed");
        
        emit OrderRefunded(orderId, amount, reason);
    }
    
    /**
     * 管理员仲裁 —— 放款给卖家（争议后判定卖家胜）
     * @param orderId 订单 ID
     */
    function arbitrateRelease(bytes32 orderId) external onlyOwner {
        Order storage order = orders[orderId];
        require(
            order.status == OrderStatus.Disputed,
            "Order not disputed"
        );
        
        order.status = OrderStatus.Confirmed;
        uint256 amount = order.amount;
        order.amount = 0;
        totalReleased += amount;
        
        (bool ok, ) = payable(order.seller).call{value: amount}("");
        require(ok, "Transfer to seller failed");
        
        emit OrderConfirmed(orderId, amount);
    }
    
    /**
     * 查询订单
     */
    function getOrder(bytes32 orderId) external view returns (
        address buyer,
        address seller,
        string memory serviceId,
        uint256 amount,
        uint256 createdAt,
        uint256 deliveredAt,
        uint256 timeoutAt,
        OrderStatus status,
        string memory deliverResult
    ) {
        Order storage o = orders[orderId];
        return (o.buyer, o.seller, o.serviceId, o.amount, o.createdAt, o.deliveredAt, o.timeoutAt, o.status, o.deliverResult);
    }
    
    /**
     * 获取订单总数
     */
    function getOrderCount() external view returns (uint256) {
        return allOrderIds.length;
    }
    
    /**
     * 更新默认超时时间
     */
    function setDefaultTimeout(uint256 newTimeout) external onlyOwner {
        require(newTimeout > 0, "Timeout must > 0");
        emit TimeoutUpdated(defaultTimeout, newTimeout);
        defaultTimeout = newTimeout;
    }
    
    /**
     * 转移管理员
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }
    
    /**
     * 接收 BNB
     */
    receive() external payable {}
}
