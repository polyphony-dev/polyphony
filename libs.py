single_port_ram ="""
module SinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_DEPTH = 1 << ADDR_WIDTH
)
(
  input CLK,
  input RST,
  input [ADDR_WIDTH-1:0] ADDR,
  input [DATA_WIDTH-1:0] D,
  input WE,
  output [DATA_WIDTH-1:0] Q
);

  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  assign Q = mem[read_addr];
  always @ (posedge CLK) begin
    if (WE)
      mem[ADDR] <= D;
	read_addr <= ADDR;
  end
endmodule
"""

bidirectional_single_port_ram ="""
module BidirectionalSinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_LENGTH = 16,
  parameter RAM_DEPTH = 1 << ADDR_WIDTH
)
(
  input CLK,
  input RST,
  input [ADDR_WIDTH-1:0] ADDR,
  input [DATA_WIDTH-1:0] D,
  input WE,
  output [DATA_WIDTH-1:0] Q,
  output [ADDR_WIDTH-1:0] LEN
);

  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  function [ADDR_WIDTH-1:0] address (
    input [ADDR_WIDTH-1:0] in_addr
  );
  begin
    if (in_addr[ADDR_WIDTH-1] == 1'b1) begin
      address = RAM_LENGTH + in_addr;
	end else begin
      address = in_addr;
    end
  end
  endfunction // address
  wire [ADDR_WIDTH-1:0] a;
  assign a = address(ADDR);
  assign Q = mem[read_addr];
  assign LEN = RAM_LENGTH;
  always @ (posedge CLK) begin
    if (WE)
      mem[ADDR] <= D;
	read_addr <= a;
  end
endmodule
"""
