<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet 
  version="3.0"
  xmlns:tei="http://www.tei-c.org/ns/1.0" 
  xmlns:hei="https://digi.ub.uni-heidelberg.de/schema/tei/heiEDITIONS"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  >

<!-- 
    
-->  
     
  <xsl:output method="html"/>

  <!-- Identity template -->
  <xsl:mode on-no-match="shallow-copy" />

  
  
    <xsl:template match="tei:TEI | tei:text | tei:front | tei:lg">
        <div>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = tokenize('ana rendition')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
            <xsl:apply-templates select="node()"/>
        </div>    
    </xsl:template>

    <xsl:template match="tei:lb">
        <span class="tei-lb"/>
    </xsl:template>

    <xsl:template match="tei:l | tei:p | tei:titlePart">
        <div class="synoptic-unit">
            <xsl:apply-templates select="tei:gap[@corresp]">
                <xsl:with-param name="data-container-id" select="@xml:id"/>
            </xsl:apply-templates>
            <div class="tei-container-n">    
                <xsl:attribute name="data-container-id" select="@xml:id"/>
                <xsl:value-of select="@n"/>
            </div>            
            <div class="tei-container-content">
                <xsl:apply-templates select="node() except tei:gap[@corresp]"/>
            </div>
        </div>
    </xsl:template>

    <xsl:template match="tei:pb | tei:cb">
        <span>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = ('ana', 'rendition', 'facs', 'n')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="name()"/>
                        <xsl:text>-</xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
        </span>
    </xsl:template>

    <xsl:template match="tei:gap[@corresp]">
        <xsl:param name="data-container-id"/>
        <div>
            <xsl:attribute name="class">tei-gap-synoptic</xsl:attribute>
            <xsl:choose>
                <xsl:when test="$data-container-id">
                    <xsl:attribute name="data-container-id" select="$data-container-id"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:attribute name="data-container-id" select="'A'"/>
                </xsl:otherwise>
            </xsl:choose>
            <xsl:attribute name="data-link" select="@corresp"/>
            <xsl:text>◎</xsl:text>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:gap[not(@corresp)]">
        <span class="tei-gap">[…]</span>
    </xsl:template>

    
    
  
  
  
</xsl:stylesheet>
