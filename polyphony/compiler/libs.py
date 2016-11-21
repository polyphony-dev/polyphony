single_port_ram ="""
module SinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_DEPTH = 1 << ADDR_WIDTH
)
(
  input clk,
  input rst,
  input [ADDR_WIDTH-1:0] ram_addr,
  input [DATA_WIDTH-1:0] ram_d,
  input ram_we,
  output [DATA_WIDTH-1:0] ram_q
);

  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  assign ram_q = mem[read_addr];
  always @ (posedge clk) begin
    if (ram_we)
      mem[ram_addr] <= ram_d;
	read_addr <= ram_addr;
  end
endmodule
"""

bidirectional_single_port_ram ="""
module BidirectionalSinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_LENGTH = 16,
  parameter RAM_DEPTH = 1 << (ADDR_WIDTH-1)
)
(
  input clk,
  input rst,
  input [ADDR_WIDTH-1:0] ram_addr,
  input [DATA_WIDTH-1:0] ram_d,
  input ram_we,
  output [DATA_WIDTH-1:0] ram_q,
  output [ADDR_WIDTH-1:0] ram_len
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
  assign a = address(ram_addr);
  assign ram_q = mem[read_addr];
  assign ram_len = RAM_LENGTH;
  always @ (posedge clk) begin
    if (ram_we)
      mem[ram_addr] <= ram_d;
	read_addr <= a;
  end
endmodule
"""
